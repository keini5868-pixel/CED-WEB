"""Ejecutor server-side de tools de voz — usado por Retell webhooks."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any
from app.services.gemini_images import generate_image
from app.services.conversation_memory import (
    format_recall_for_voice,
    recall_previous_conversations,
    save_long_term_memory,
)
from app.services.gemini_grounded import fetch_voice_brief_parallel
from app.services.voice_spoken import (
    fit_voice_spoken,
    format_vision_response,
    voice_spoken_limit,
    voice_spoken_limit_for_kind,
)
from app.services.internal_knowledge import format_hits_for_prompt, search_internal_knowledge
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.navigation_maps import compute_route, geocode_address, search_nearby_places
from app.services.navigation_session import (
    clear_navigation,
    clear_navigation_pending,
    clear_place_options,
    get_current_step_index,
    get_location,
    get_place_options,
    get_route,
    push_client_action,
    set_navigating,
    set_place_options,
    set_route,
)
from app.services.cognitive_memory import save_memory, search_memory
from app.services.pdf_report import (
    assistant_fallback_texts_from_messages,
    normalize_pdf_fields,
    store_pdf,
)
from app.services.prospection import get_prospection_report, set_prospection_enabled
from app.services.social_comments import fetch_social_comments
from app.services.user_address import sync_address_from_memory_key
from app.services import voice_client_session as vcs
from app.services.voice_usage import voice_access_state

logger = logging.getLogger(__name__)

SEARCH_WEB_TIMEOUT_SEC = 17.0
VISION_PIPELINE_TIMEOUT_SEC = 45.0
PUBLISH_TIMEOUT_SEC = 30.0
NAVIGATION_TIMEOUT_SEC = 25.0


def _parse_place_option_index(params: dict[str, Any]) -> int | None:
    raw = params.get("index")
    if raw is not None:
        try:
            idx = int(raw)
            if idx >= 0:
                return idx
        except (TypeError, ValueError):
            pass
    text = " ".join(
        str(params.get(k) or "")
        for k in ("opcion", "option", "eleccion", "destino", "query", "texto")
    ).lower()
    if re.search(r"\b(primero|primera|1|uno)\b", text):
        return 0
    if re.search(r"\b(segundo|segunda|2|dos)\b", text):
        return 1
    if re.search(r"\b(tercero|tercera|3|tres)\b", text):
        return 2
    if re.search(r"\b(m[aá]s cercano|m[aá]s pr[oó]ximo|el cercano|la cercana)\b", text):
        return 0
    return None


def _format_places_spoken(places: list[dict[str, Any]], *, query: str) -> str:
    if not places:
        return f"No encontré {query} cerca, señor."
    count = len(places)
    lead = (
        f"Señor, encontré {count} {query} cercanos."
        if count > 1
        else f"Señor, encontré un {query} cercano."
    )
    first = places[0]
    name = str(first.get("name") or query)
    dist = str(first.get("distance_text") or "")
    addr = str(first.get("address") or "")
    street = addr.split(",")[0].strip() if addr else name
    detail = f" El más próximo está a {dist} en {street}." if dist else f" El más próximo es {name}."
    if count > 1:
        detail += " ¿Cuál prefiere o iniciamos con el más cercano?"
    else:
        detail += " ¿Inicio el viaje?"
    return fit_voice_spoken(f"{lead}{detail}")


def _push_map_start_navigation(
    user_id: str,
    *,
    destination: str,
    index: int | None = None,
    action: str = "apply_route",
    route: dict[str, Any] | None = None,
) -> None:
    from app.services import voice_client_session as vcs

    event: dict[str, Any] = {
        "type": "map_start_navigation",
        "destination": destination,
        "action": action,
    }
    if index is not None:
        event["index"] = index
    if route is not None:
        event["route"] = route
    vcs.push_tool_event(user_id, event)


def _begin_active_navigation(user_id: str, route: dict[str, Any]) -> dict[str, Any]:
    set_navigating(user_id, True)
    clear_navigation_pending(user_id)
    push_client_action(user_id, "begin_navigation", {})
    dest_label = str(route.get("destination", {}).get("label") or "su destino")
    _push_map_start_navigation(
        user_id,
        destination=dest_label,
        action="begin_navigation",
    )
    return {
        "ok": True,
        "spoken": f"Iniciando navegación hacia {dest_label}, señor.",
        "client_action": "begin_navigation",
    }


async def _start_route_for_user(
    user_id: str,
    *,
    dest_lat: float,
    dest_lng: float,
    dest_label: str,
    index: int | None = None,
) -> dict[str, Any]:
    loc = get_location(user_id)
    if not loc:
        push_client_action(user_id, "open_drive", {})
        return {
            "ok": True,
            "spoken": "Abro el mapa primero, señor. Active ubicación y repita el destino.",
            "client_action": "open_drive",
        }
    route = await asyncio.to_thread(
        compute_route,
        origin_lat=float(loc["lat"]),
        origin_lng=float(loc["lng"]),
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        dest_label=dest_label,
    )
    if not route.get("ok"):
        return _spoken_err(
            str(route.get("error") or "No pude calcular la ruta, señor."),
            error="route_failed",
        )
    set_route(user_id, route)
    set_navigating(user_id, False)
    clear_place_options(user_id)
    clear_navigation_pending(user_id)
    push_client_action(user_id, "apply_route", route)
    _push_map_start_navigation(
        user_id,
        destination=dest_label,
        index=index,
        action="apply_route",
        route=route,
    )
    spoken = fit_voice_spoken(
        f"Ruta lista hacia {dest_label}, señor. "
        f"{route.get('duration_text', '')} · {route.get('distance_text', '')}. "
        f"Dígame «iniciar» o pulse Iniciar cuando quiera."
    )
    return {
        "ok": True,
        "spoken": spoken,
        "client_action": "apply_route",
        "route": route,
    }


class SearchWebState:
    """Evita procesar más de una respuesta search_web por invocación."""

    def __init__(self) -> None:
        self.responded = False
        self.response_id: str | None = None

    def take(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.responded:
            logger.warning(
                "[SEARCH] respuesta duplicada descartada (id=%s)",
                self.response_id,
            )
            return None
        self.responded = True
        self.response_id = str(payload.get("response_id") or uuid.uuid4())[:8]
        return payload


async def _wait_camera_ack(user_id: str, timeout_sec: float = 8.0) -> bool:
    """Espera ACK del cliente: camera_active + camera_stream_present."""
    import time

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if vcs.is_camera_active(user_id):
            status = vcs.get_camera_status(user_id)
            logger.info(
                "[CAMERA] ack=true user=%s active=%s stream=%s age=%.1fs",
                user_id[:8],
                status.get("camera_active"),
                status.get("camera_stream_present"),
                float(status.get("age_sec") or 0),
            )
            return True
        await asyncio.sleep(0.2)
    status = vcs.get_camera_status(user_id)
    logger.warning(
        "[CAMERA] ack=timeout user=%s active=%s stream=%s age=%.1fs",
        user_id[:8],
        status.get("camera_active"),
        status.get("camera_stream_present"),
        float(status.get("age_sec") or 0),
    )
    return False


async def _wait_camera_active(user_id: str, timeout_sec: float = 5.0) -> bool:
    return await _wait_camera_ack(user_id, timeout_sec)


async def handle_camera_activation(
    user_id: str,
    *,
    fast: bool = False,
) -> dict[str, Any]:
    """Pide al cliente activar cámara; fast=True responde al instante sin bloquear."""
    if vcs.is_camera_active(user_id):
        return _spoken_ok("Cámara activa, señor. Lista para analizar.")
    vcs.push_client_action(user_id, "camera_activate", {})
    vcs.push_tool_event(user_id, {"type": "camera_activate"})
    if fast:
        return _spoken_ok("Cámara activa, señor. Lista para analizar.")
    active = await _wait_camera_ack(user_id, 8.0)
    if active or vcs.is_camera_active(user_id):
        return _spoken_ok("Cámara activa, señor. Lista para analizar.")
    return _spoken_err(
        "No pude activar la cámara, señor. Verifique permisos.",
        error="camera_activation_timeout",
    )


async def _wait_vision_result(
    user_id: str, request_id: int, timeout_sec: float = 24.0
) -> str | None:
    import time

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        result = vcs.pop_vision_result(user_id, request_id)
        if result:
            return result
        await asyncio.sleep(0.35)
    return None


async def _run_camera_capture(
    user_id: str,
    *,
    question: str,
    mode: str,
) -> dict[str, Any]:
    import time

    request_id = int(time.time() * 1000)
    logger.info(
        "[CAMERA] capture_start user=%s mode=%s request_id=%s q=%s",
        user_id[:8],
        mode,
        request_id,
        question[:80],
    )
    if not vcs.is_camera_active(user_id):
        logger.info("[CAMERA] auto_activate user=%s", user_id[:8])
        vcs.push_client_action(user_id, "camera_activate", {})
        ack = await _wait_camera_ack(user_id, 8.0)
        logger.info("[CAMERA] auto_activate_ack user=%s ok=%s", user_id[:8], ack)

    vcs.push_client_action(
        user_id,
        "camera_capture",
        {"request_id": request_id, "question": question, "mode": mode},
    )
    logger.info("[CAMERA] capture_pushed user=%s request_id=%s", user_id[:8], request_id)
    summary = await _wait_vision_result(
        user_id, request_id, timeout_sec=VISION_PIPELINE_TIMEOUT_SEC
    )
    if summary:
        logger.info(
            "[VISION:GEMINI] capture_ok user=%s request_id=%s len=%s",
            user_id[:8],
            request_id,
            len(summary),
        )
        formatted = format_vision_response(summary) or summary.strip()
        vcs.set_last_vision_summary(user_id, formatted)
        return _spoken_ok(formatted)
    logger.warning(
        "[VISION:GEMINI] capture_timeout user=%s request_id=%s",
        user_id[:8],
        request_id,
    )
    return _spoken_err(
        "Señor, no pude capturar la imagen. Intente mostrar de nuevo.",
        error="camera_capture_timeout",
    )


def _spoken_ok(text: str, *, max_chars: int | None = None) -> dict[str, Any]:
    return {"ok": True, "spoken": fit_voice_spoken(text, max_chars=max_chars)}


def _spoken_err(text: str, *, error: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "spoken": text}
    if error:
        out["error"] = error
    return out


def _resolve_image_for_publishing(
    user_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    from app.services.publish_image_context import resolve_image_for_publishing

    conversation_id = str(
        params.get("conversation_id") or params.get("session_id") or ""
    ).strip() or None
    return resolve_image_for_publishing(
        user_id,
        conversation_id,
        session_id=conversation_id,
        explicit_image_id=str(params.get("image_id") or "").strip() or None,
        use_last_uploaded_image=params.get("use_last_image", True) is not False,
        image_url=params.get("image_url"),
        image_data=params.get("image_data"),
    )


def _load_reference_image_bytes(
    user_id: str,
    params: dict[str, Any],
) -> tuple[bytes, str] | None:
    """Resuelve bytes de imagen de referencia desde sesión voz, chat o parámetros."""
    from app.services.publish_media import decode_image_data

    resolved = _resolve_image_for_publishing(user_id, params)
    if resolved.get("ok"):
        data = str(resolved.get("data") or "").strip()
        url = str(resolved.get("url") or "").strip()
        if data:
            try:
                raw, mime = decode_image_data(data)
                if raw:
                    return raw, mime
            except Exception:  # noqa: BLE001
                pass
        if url:
            try:
                raw, mime = decode_image_data(url)
                if raw:
                    return raw, mime
            except Exception:  # noqa: BLE001
                pass

    stored = vcs.get_last_publishable_image(user_id, ignore_call_binding=True)
    if stored:
        data = str(stored.get("data") or "").strip()
        url = str(stored.get("url") or "").strip()
        if data:
            try:
                raw, mime = decode_image_data(data)
                if raw:
                    return raw, mime
            except Exception:  # noqa: BLE001
                pass
        if url:
            try:
                raw, mime = decode_image_data(url)
                if raw:
                    return raw, mime
            except Exception:  # noqa: BLE001
                pass
    return None


async def _run_publish_call(
    fn: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=PUBLISH_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.error("[PUBLISH] timeout en %s", getattr(fn, "__name__", "publish"))
        return {
            "ok": False,
            "spoken": (
                "Señor, la publicación está tardando más de lo normal. "
                "¿Desea que lo intente de nuevo?"
            ),
            "error": "timeout",
        }
    except MetaSocialError as exc:
        logger.error("[PUBLISH] Meta error: %s", exc)
        return {
            "ok": False,
            "spoken": f"Señor, no pude publicar. {str(exc)[:100]}",
            "error": "publish_failed",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("[PUBLISH] error: %s", exc)
        return {
            "ok": False,
            "spoken": f"Señor, hubo un problema publicando. {str(exc)[:100]}",
            "error": "publish_failed",
        }


async def execute_voice_tool(
    tool_name: str,
    user_id: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ejecuta una tool CED y devuelve resultado + mensaje hablable."""
    name = (tool_name or "").strip()
    params = args or {}
    if not user_id:
        return _spoken_err("No identifiqué al usuario, señor.", error="missing_user_id")

    try:
        if name == "search_web":
            query = str(params.get("query") or "").strip()
            kind = str(params.get("kind") or "general")
            from app.services.cognitive_intents import (
                is_internal_knowledge_query,
                is_web_research_intent,
                requires_live_web,
            )

            must_use_live_web = (
                kind in ("news", "weather")
                or requires_live_web(query)
                or is_web_research_intent(query)
            )
            if not must_use_live_web and is_internal_knowledge_query(query):
                hits = search_internal_knowledge(query, limit=2)
                if hits:
                    internal = format_hits_for_prompt(hits)
                    return _spoken_ok(internal)
                return _spoken_ok(
                    "Con gusto, señor. Puedo explicarle eso con lo que ya tengo en mi cerebro interno."
                )
            web_state = SearchWebState()
            try:
                result = await asyncio.wait_for(
                    fetch_voice_brief_parallel(query, kind=kind),
                    timeout=SEARCH_WEB_TIMEOUT_SEC,
                )
            except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
                logger.warning("[WEB_SEARCH] fallback: %s", exc)
                payload = web_state.take(
                    {
                        "status": "timeout",
                        "fallback": True,
                        "ok": False,
                        "spoken": "Búsqueda agotada.",
                    }
                )
                return payload or {
                    "status": "timeout",
                    "fallback": True,
                    "ok": False,
                    "spoken": "Búsqueda agotada.",
                }
            summary = str(result.get("summary") or "").strip()
            if result.get("ok") and summary:
                spoken_limit = voice_spoken_limit_for_kind(kind, query)
                payload = web_state.take(
                    {
                        "status": "success",
                        "ok": True,
                        "spoken": fit_voice_spoken(summary, max_chars=spoken_limit),
                        "summary": summary,
                        "kind": kind,
                        "source": result.get("source"),
                        "response_id": result.get("response_id"),
                    }
                )
                if payload:
                    return payload
            logger.warning(
                "[WEB_SEARCH] empty/fail kind=%s code=%s",
                kind,
                result.get("code"),
            )
            payload = web_state.take(
                {
                    "status": "timeout",
                    "fallback": True,
                    "ok": False,
                    "spoken": str(result.get("spoken") or "Sin resultados actuales disponibles."),
                }
            )
            return payload or {
                "status": "timeout",
                "fallback": True,
                "ok": False,
                "spoken": "Sin resultados actuales disponibles.",
            }


        if name == "generate_image":
            prompt = str(params.get("prompt") or "").strip()
            quality = str(params.get("quality") or "auto")
            balance = voice_access_state(user_id)
            logger.info("[VOICE:IMAGE] start user=%s prompt=%s", user_id[:8], prompt[:80])
            result = await asyncio.to_thread(
                generate_image,
                user_id=user_id,
                plan_id=str(balance.get("plan_id") or ""),
                prompt=prompt,
                quality=quality,
            )
            if result.get("ok"):
                url = str(result.get("url") or "")
                logger.info(
                    "[VOICE:IMAGE] ok user=%s provider=%s url=%s",
                    user_id[:8],
                    result.get("provider") or result.get("model"),
                    url[:120],
                )
                vcs.push_tool_event(
                    user_id,
                    {
                        "type": "generated_image",
                        "image_url": url,
                        "prompt": prompt,
                    },
                )
                return {
                    "ok": True,
                    "spoken": "Imagen generada, señor.",
                    "url": url,
                    "image_url": url,
                    "prompt": prompt,
                }
            err = str(result.get("error") or "image_failed")
            code = str(result.get("code") or "")
            logger.error(
                "[VOICE:IMAGE] fail user=%s code=%s error=%s",
                user_id[:8],
                code,
                err[:200],
            )
            if code == "config_error":
                return _spoken_err(
                    "No fue posible generar la imagen: falta configurar GOOGLE_API_KEY o OPENAI_API_KEY, señor.",
                    error=err,
                )
            if code in ("quota_exhausted", "plan_limit"):
                return _spoken_err(f"No fue posible generar la imagen, señor. {err}", error=code)
            return _spoken_err(
                f"No fue posible generar la imagen en este momento, señor. {err}".strip(),
                error=code or err,
            )

        if name == "generate_image_with_reference":
            from app.services.image_reference_generator import generate_image_with_reference

            prompt = str(params.get("prompt") or "").strip()
            style_mode = str(params.get("style_mode") or "edit")
            quality = str(params.get("quality") or "standard")
            if not prompt:
                return _spoken_err("Indique qué desea generar o cambiar en la imagen, señor.")

            ref = await asyncio.to_thread(_load_reference_image_bytes, user_id, params)
            if not ref:
                return _spoken_err(
                    "No tengo imagen de referencia en esta sesión, señor. "
                    "Suba una foto al panel de voz, muestre algo con la cámara, "
                    "o adjunte una imagen en el chat.",
                    error="missing_reference_image",
                )
            raw, mime = ref
            logger.info(
                "[VOICE:REF-IMG] start user=%s mode=%s prompt=%s",
                user_id[:8],
                style_mode,
                prompt[:80],
            )
            result = await asyncio.to_thread(
                generate_image_with_reference,
                user_id=user_id,
                prompt=prompt,
                reference_image=raw,
                content_type=mime,
                style_mode=style_mode,
                quality=quality,
            )
            if result.get("ok"):
                url = str(result.get("url") or "")
                vcs.push_tool_event(
                    user_id,
                    {
                        "type": "generated_image",
                        "image_url": url,
                        "prompt": prompt,
                    },
                )
                return {
                    "ok": True,
                    "spoken": "Imagen generada con referencia, señor.",
                    "url": url,
                    "image_url": url,
                    "prompt": prompt,
                }
            err = str(result.get("error") or "reference_image_failed")
            code = str(result.get("code") or "")
            if code in ("quota_exhausted", "plan_limit"):
                return _spoken_err(f"No fue posible generar la imagen, señor. {err}", error=code)
            return _spoken_err(
                f"No fue posible generar la imagen con referencia, señor. {err}".strip(),
                error=code or err,
            )

        if name == "save_memory":
            clave = str(params.get("clave") or params.get("key") or "").strip()
            contenido = str(params.get("contenido") or params.get("content") or "").strip()
            categoria = params.get("categoria") or params.get("category")
            if not clave or not contenido:
                return _spoken_err("No recibí qué guardar en memoria, señor.")
            await asyncio.to_thread(
                save_memory,
                user_id,
                clave,
                contenido,
                category=str(categoria) if categoria else None,
            )
            await asyncio.to_thread(sync_address_from_memory_key, user_id, clave, contenido)
            return _spoken_ok("Memoria guardada, señor.")

        if name == "recall_memory":
            consulta = str(params.get("consulta") or params.get("query") or "").strip()
            result = await asyncio.to_thread(search_memory, user_id, consulta)
            items = result.get("results") or result.get("items") or []
            if not items:
                return _spoken_ok("No encontré memorias sobre eso, señor.")
            lines = []
            for item in items[:3]:
                key = item.get("key") or item.get("clave") or "dato"
                val = item.get("content") or item.get("contenido") or ""
                lines.append(f"{key}: {val}")
            return _spoken_ok(f"Recuerdo: {'; '.join(lines)}")

        if name == "recall_previous_conversations":
            query = str(params.get("query") or "").strip()
            days_back = int(params.get("days_back") or 30)
            data = await asyncio.to_thread(
                recall_previous_conversations,
                user_id,
                query,
                days_back=days_back,
            )
            spoken = format_recall_for_voice(data)
            if spoken:
                return _spoken_ok(spoken)
            return _spoken_ok("No encontré conversaciones previas sobre eso, señor.")

        if name == "save_to_long_term_memory":
            category = str(params.get("category") or "").strip()
            key = str(params.get("key") or "").strip()
            value = str(params.get("value") or "").strip()
            importance = int(params.get("importance") or 5)
            if not category or not key or not value:
                return _spoken_err("Faltan datos para guardar en memoria a largo plazo, señor.")
            await asyncio.to_thread(
                save_long_term_memory,
                user_id,
                category=category,
                key=key,
                value=value,
                importance=importance,
            )
            return _spoken_ok("Información registrada, señor.")

        if name in ("request_camera_activation", "request_camera_deactivation"):
            if name == "request_camera_deactivation":
                vcs.push_client_action(user_id, "camera_deactivate", {})
                vcs.push_tool_event(user_id, {"type": "camera_deactivate"})
                vcs.set_camera_active(user_id, False)
                vcs.set_last_vision_summary(user_id, "")
                return _spoken_ok("Cámara desactivada, señor.")
            fast = bool(params.get("fast"))
            return await handle_camera_activation(user_id, fast=fast)

        if name == "analyze_uploaded_image":
            from app.services.chat_multimedia import analyze_chat_image
            from app.services.publish_media import decode_image_data

            pregunta = str(
                params.get("pregunta") or params.get("question") or "¿Qué hay en esta imagen?"
            ).strip()
            stored = vcs.get_last_publishable_image(user_id)
            if not stored or not stored.get("url"):
                return _spoken_err(
                    "No hay imagen subida en esta sesión, señor. "
                    "Use el botón «Subir imagen a CED» en el panel.",
                    error="missing_uploaded_image",
                )
            try:
                raw, mime = decode_image_data(str(stored["url"]))
                spoken = await asyncio.to_thread(
                    analyze_chat_image,
                    user_id,
                    image_bytes=raw,
                    media_type=mime,
                    user_text=pregunta,
                )
                return _spoken_ok(spoken)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[VOICE:IMAGE] analyze_uploaded failed user=%s: %s", user_id[:8], exc)
                return _spoken_err("No pude analizar la imagen subida, señor.")

        if name == "analyze_camera_frame":
            pregunta = str(
                params.get("pregunta") or params.get("question") or "¿Qué ves en la imagen?"
            ).strip()
            return await _run_camera_capture(user_id, question=pregunta, mode="analyze")

        if name == "buscar_lo_visible":
            pregunta = str(params.get("pregunta") or params.get("question") or "").strip()
            return await _run_camera_capture(
                user_id,
                question=pregunta or "Identifica lo visible y busca información",
                mode="visual_search",
            )

        if name == "generar_pdf":
            from app.deps.plan_access import effective_plan_limits

            limits, reason, _ = effective_plan_limits(user_id)
            if reason == "trial_expired":
                return _spoken_err("Tu prueba terminó, señor. Elige un plan en Precios.")
            if not limits.pdf_reports:
                return _spoken_err(
                    "Los PDFs requieren plan Élite o Founding, señor. Mejora en Precios."
                )
            titulo, contenido = normalize_pdf_fields(params)
            fallbacks = params.get("_pdf_fallback_texts")
            fallback_list = fallbacks if isinstance(fallbacks, list) else None
            user_request = str(
                params.get("_user_request")
                or params.get("user_request")
                or params.get("query")
                or titulo
            ).strip()
            try:
                artifact = await asyncio.to_thread(
                    store_pdf,
                    user_id=user_id,
                    title=titulo,
                    content=contenido,
                    fallback_texts=fallback_list,
                    user_request=user_request,
                )
            except ValueError:
                return _spoken_err(
                    "No pude redactar el contenido del PDF, señor. "
                    "Repita qué desea incluir en el documento.",
                    error="pdf_empty_content",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("[VOICE:PDF] store failed user=%s", user_id[:8])
                msg = str(exc).strip() or "pdf_store_failed"
                return _spoken_err(
                    f"No pude generar el PDF, señor. Detalle: {msg[:100]}.",
                    error="pdf_store_failed",
                )
            spoken = (
                f"PDF listo, señor. Título: {artifact.title}. "
                "¿Dónde desea guardarlo?"
            )
            try:
                vcs.push_tool_event(
                    user_id,
                    {
                        "type": "pdf_created",
                        "title": artifact.title,
                        "file_id": artifact.file_id,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.warning("[VOICE:PDF] push_tool_event failed user=%s", user_id[:8])
            return {
                "ok": True,
                "spoken": spoken,
                "file_id": artifact.file_id,
                "title": artifact.title,
            }

        if name in ("leer_gmail", "enviar_gmail"):
            from app.modules.gmail_module import handle_gmail_query_sync

            if name == "leer_gmail":
                query = str(
                    params.get("consulta")
                    or params.get("query")
                    or params.get("_user_request")
                    or ""
                ).strip()
                if not query:
                    query = "léeme mis correos"
            else:
                dest = str(
                    params.get("destinatario") or params.get("to") or ""
                ).strip()
                msg = str(params.get("mensaje") or params.get("body") or "").strip()
                if not dest or not msg:
                    return _spoken_err(
                        "Señor, indique a quién enviar el correo y el mensaje.",
                        error="gmail_missing_fields",
                    )
                query = f"envía un email a {dest} diciendo {msg}"
            result = await asyncio.to_thread(handle_gmail_query_sync, user_id, query)
            spoken = str(result.get("spoken") or "").strip()
            if spoken:
                return _spoken_ok(spoken)
            return _spoken_err("No pude acceder a Gmail, señor.", error="gmail_failed")

        if name == "leer_comentarios_redes":
            platform = str(params.get("platform") or "both")
            result = await asyncio.to_thread(
                fetch_social_comments,
                user_id,
                platform=platform,
            )
            spoken = str(result.get("spoken") or "").strip()
            if result.get("ok"):
                return {
                    "ok": True,
                    "spoken": spoken or "Consulta de comentarios completada, señor.",
                    "count": result.get("count", 0),
                }
            return _spoken_err(
                spoken or "No fue posible leer comentarios, señor.",
                error=str(result.get("error") or "comments_failed"),
            )

        if name == "consultar_redes_conectadas":
            from app.services import supabase_db

            conn = supabase_db.get_meta_connection(user_id)
            if not conn or not conn.get("access_token"):
                return _spoken_ok(
                    "No tiene redes Meta conectadas, señor. "
                    "Puede vincular Facebook e Instagram en Conectar Redes del dashboard."
                )
            ig = str(conn.get("ig_username") or "Instagram").strip()
            return _spoken_ok(
                f"Tiene Meta conectado, señor. Instagram @{ig}. "
                "Puede publicar cuando confirme el texto del post."
            )

        if name == "activar_prospeccion":
            from app.deps.plan_access import effective_plan_limits

            limits, reason, _ = effective_plan_limits(user_id)
            if reason == "trial_expired":
                return _spoken_err("Tu prueba terminó, señor. Elige un plan en Precios.")
            if not limits.prospection_enabled:
                return _spoken_err(
                    "La prospección requiere plan Élite o Founding, señor. Mejora en Precios."
                )
            vcs.set_active_mode(user_id, "prospect")
            result = await asyncio.to_thread(set_prospection_enabled, user_id, True)
            if result.get("ok"):
                return _spoken_ok("Sistema de prospección activado, señor.")
            return _spoken_err("No fue posible activar prospección, señor.")

        if name == "desactivar_prospeccion":
            result = await asyncio.to_thread(set_prospection_enabled, user_id, False)
            if result.get("ok"):
                return _spoken_ok("Prospección desactivada, señor.")
            return _spoken_err("No fue posible desactivar prospección, señor.")

        if name == "reporte_prospeccion":
            result = await asyncio.to_thread(get_prospection_report, user_id)
            spoken = str(result.get("spoken") or "Sin datos de prospección.")
            return _spoken_ok(spoken)

        if name == "publicar_facebook":
            from app.services.publish_text import sanitize_publish_caption, validate_caption

            logger.info("[PUBLISH] inicio publicar_facebook user=%s", user_id[:8])
            mensaje = sanitize_publish_caption(str(params.get("mensaje") or ""))
            logger.info("[PUBLISH] caption recibido: '%s'", mensaje[:120])
            is_valid, reason = validate_caption(mensaje)
            if not is_valid:
                logger.warning("[PUBLISH] caption inválido voice FB: %s", reason)
                return _spoken_err(
                    "Señor, eso parece una instrucción, no el texto final. "
                    "Genero un guion sobre el tema, se lo propongo y publico solo tras su confirmación.",
                    error="invalid_caption",
                )
            image_url = params.get("image_url")
            image_data = params.get("image_data")
            if not image_url and not image_data:
                session_id = str(
                    params.get("conversation_id") or params.get("session_id") or ""
                ).strip() or "?"
                logger.info("[PUBLISH] resolviendo imagen para session=%s user=%s", session_id, user_id[:8])
                resolved = _resolve_image_for_publishing(user_id, params)
                if resolved.get("ok"):
                    image_url = resolved.get("url")
                    image_data = resolved.get("data")
            logger.info(
                "[PUBLISH] imagen resuelta: %s user=%s",
                (str(image_url or image_data or "NONE"))[:120],
                user_id[:8],
            )
            logger.info("[PUBLISH] enviando a Meta API facebook user=%s", user_id[:8])
            result = await _run_publish_call(
                publish_facebook,
                user_id,
                mensaje,
                image_url=str(image_url) if image_url else None,
                image_data=str(image_data) if image_data else None,
            )
            logger.info("[PUBLISH] fin publicar_facebook ok=%s user=%s", result.get("ok"), user_id[:8])
            logger.info("[PUBLISH] respuesta Meta: %s", str(result.get("spoken") or result.get("error") or "")[:160])
            if not result.get("ok"):
                return _spoken_err(str(result.get("spoken") or "No pude publicar."), error=str(result.get("error")))
            spoken = str(result.get("spoken") or "Publicación enviada con éxito a Facebook, señor.")
            return _spoken_ok(spoken)

        if name == "publicar_instagram":
            from app.services.publish_text import sanitize_publish_caption, validate_caption

            logger.info("[PUBLISH] inicio publicar_instagram user=%s", user_id[:8])
            caption = sanitize_publish_caption(str(params.get("caption") or ""))
            logger.info("[PUBLISH] caption recibido: '%s'", caption[:120])
            image_url = params.get("image_url")
            image_data = params.get("image_data")

            if not image_url and not image_data:
                session_id = str(
                    params.get("conversation_id") or params.get("session_id") or ""
                ).strip() or "?"
                logger.info("[PUBLISH] resolviendo imagen para session=%s user=%s", session_id, user_id[:8])
                resolved = _resolve_image_for_publishing(user_id, params)
                if resolved.get("ok"):
                    image_url = resolved.get("url")
                    image_data = resolved.get("data")
            logger.info(
                "[PUBLISH] imagen resuelta: %s user=%s",
                (str(image_url or image_data or "NONE"))[:120],
                user_id[:8],
            )
            if not caption and (image_url or image_data):
                return {
                    "ok": False,
                    "spoken": "Imagen recibida, señor. ¿Qué texto desea que acompañe su publicación?",
                    "error": "missing_caption",
                }
            if not image_url and not image_data:
                return {
                    "ok": False,
                    "spoken": (
                        "No encuentro la imagen para publicar, señor. "
                        "Adjúntela en el chat o muéstremela con la cámara activa."
                    ),
                    "error": "missing_image",
                }
            is_valid, reason = validate_caption(caption)
            if not is_valid:
                logger.warning("[PUBLISH] caption inválido voice IG: %s", reason)
                return _spoken_err(
                    "Señor, eso parece una instrucción, no el texto final. "
                    "Genero un guion sobre el tema, se lo propongo y publico solo tras su confirmación.",
                    error="invalid_caption",
                )
            logger.info("[PUBLISH] enviando a Meta API instagram user=%s", user_id[:8])
            result = await _run_publish_call(
                publish_instagram,
                user_id,
                caption,
                image_url=str(image_url) if image_url else None,
                image_data=str(image_data) if image_data else None,
            )
            logger.info("[PUBLISH] fin publicar_instagram ok=%s user=%s", result.get("ok"), user_id[:8])
            logger.info("[PUBLISH] respuesta Meta: %s", str(result.get("spoken") or result.get("error") or "")[:160])
            if not result.get("ok"):
                return _spoken_err(str(result.get("spoken") or "No pude publicar."), error=str(result.get("error")))
            spoken = str(result.get("spoken") or "Publicación enviada con éxito a Instagram, señor.")
            vcs.clear_awaiting_instagram_caption(user_id)
            vcs.clear_last_publishable_image(user_id)
            return _spoken_ok(spoken)

        if name == "activar_modo_conducir":
            vcs.set_active_mode(user_id, "map")
            vcs.set_map_search_results(user_id, [])
            clear_navigation_pending(user_id)
            push_client_action(user_id, "open_drive", {})
            return {
                "ok": True,
                "spoken": "Abriendo el mapa y modo conducir, señor.",
                "client_action": "open_drive",
            }

        if name == "search_nearby_places":
            query = str(
                params.get("query") or params.get("place") or params.get("destino") or ""
            ).strip()
            if not query:
                return _spoken_err("No escuché qué lugar buscar cerca, señor.")
            from app.services.navigation_voice_intent import (
                is_plausible_place_query,
                normalize_navigation_query,
            )

            user_request = str(params.get("_user_request") or params.get("user_request") or "").strip()
            query = normalize_navigation_query(query, context=user_request)
            if not is_plausible_place_query(query, user_text=user_request or query):
                return _spoken_ok(
                    "Señor, no identifiqué un destino de navegación. "
                    "¿A qué lugar cercano desea ir?"
                )
            loc = get_location(user_id)
            if not loc:
                push_client_action(user_id, "open_drive", {})
                if vcs.get_active_mode(user_id) == "map":
                    spoken = (
                        "Señor, active la ubicación en el navegador y repita el destino."
                    )
                else:
                    spoken = (
                        "Abro el mapa, señor. Active ubicación y repita a dónde desea ir."
                    )
                return {
                    "ok": True,
                    "spoken": spoken,
                    "client_action": "open_drive",
                }
            found = await asyncio.to_thread(
                search_nearby_places,
                query,
                origin_lat=float(loc["lat"]),
                origin_lng=float(loc["lng"]),
                limit=3,
            )
            if not found.get("ok"):
                return _spoken_err(
                    str(found.get("error") or "No encontré ese lugar cerca, señor."),
                    error="places_failed",
                )
            places = list(found.get("places") or [])
            vcs.set_active_mode(user_id, "map")
            set_place_options(user_id, places, query=query)
            vcs.set_map_search_results(user_id, places)
            push_client_action(
                user_id,
                "show_place_options",
                {"query": query, "places": places},
            )
            vcs.push_tool_event(
                user_id,
                {
                    "type": "map_search_results",
                    "query": query,
                    "places": places,
                },
            )
            return {
                "ok": True,
                "spoken": _format_places_spoken(places, query=query),
                "client_action": "show_place_options",
                "places": places,
            }

        if name in {"start_navigation", "iniciar_navegacion"}:
            option_idx = _parse_place_option_index(params)
            options = get_place_options(user_id)
            if option_idx is not None and options:
                if option_idx >= len(options):
                    return _spoken_err("Esa opción no está disponible, señor.")
                place = options[option_idx]
                return await _start_route_for_user(
                    user_id,
                    dest_lat=float(place["lat"]),
                    dest_lng=float(place["lng"]),
                    dest_label=str(place.get("name") or place.get("address") or "Destino"),
                    index=option_idx,
                )
            destino = str(params.get("destino") or params.get("query") or "").strip()
            confirm_words = {
                "iniciar",
                "ir",
                "vamos",
                "adelante",
                "dale",
                "listo",
                "confirmar",
                "start",
                "go",
                "arrancar",
                "iniciar navegacion",
                "iniciar navegación",
                "iniciar ruta",
            }
            existing_route = get_route(user_id)
            explicit_confirm = params.get("confirm") is True
            if existing_route and (
                explicit_confirm or destino.lower() in confirm_words
            ):
                return _begin_active_navigation(user_id, existing_route)
            if not destino:
                if existing_route:
                    dest_label = str(
                        existing_route.get("destination", {}).get("label") or "su destino"
                    )
                    return _spoken_ok(
                        f"Ruta lista hacia {dest_label}, señor. "
                        f"Dígame «iniciar» o pulse Iniciar cuando quiera."
                    )
                if options:
                    return _spoken_ok(
                        "Tiene opciones en pantalla, señor. Diga el primero, el segundo "
                        "o toque Iniciar viaje."
                    )
                return _spoken_err("No escuché el destino, señor.")
            loc = get_location(user_id)
            if not loc:
                push_client_action(user_id, "open_drive", {})
                return {
                    "ok": True,
                    "spoken": (
                        "Abro el mapa primero, señor. Active ubicación y repita el destino."
                    ),
                    "client_action": "open_drive",
                }
            if len(destino.split()) <= 4 and not re.search(r"\d", destino):
                found = await asyncio.to_thread(
                    search_nearby_places,
                    destino,
                    origin_lat=float(loc["lat"]),
                    origin_lng=float(loc["lng"]),
                    limit=3,
                )
                if found.get("ok") and found.get("places"):
                    places = list(found.get("places") or [])
                    set_place_options(user_id, places, query=destino)
                    push_client_action(
                        user_id,
                        "show_place_options",
                        {"query": destino, "places": places},
                    )
                    return {
                        "ok": True,
                        "spoken": _format_places_spoken(places, query=destino),
                        "client_action": "show_place_options",
                        "places": places,
                    }
            geo = await asyncio.to_thread(
                geocode_address,
                destino,
                bias_lat=float(loc["lat"]),
                bias_lng=float(loc["lng"]),
            )
            if not geo.get("ok"):
                return _spoken_err(
                    str(geo.get("error") or "No encontré el destino, señor."),
                    error="geocode_failed",
                )
            return await _start_route_for_user(
                user_id,
                dest_lat=float(geo["lat"]),
                dest_lng=float(geo["lng"]),
                dest_label=str(geo.get("formatted_address") or destino),
            )

        if name == "buscar_direccion":
            query = str(params.get("query") or params.get("destino") or "").strip()
            if not query:
                return _spoken_err("No escuché qué dirección buscar, señor.")
            loc = get_location(user_id)
            geo = await asyncio.to_thread(
                geocode_address,
                query,
                bias_lat=float(loc["lat"]) if loc else None,
                bias_lng=float(loc["lng"]) if loc else None,
            )
            if not geo.get("ok"):
                return _spoken_err(
                    str(geo.get("error") or "No encontré esa dirección, señor."),
                    error="geocode_failed",
                )
            label = str(geo.get("formatted_address") or query)
            payload = {"lat": geo["lat"], "lng": geo["lng"], "label": label}
            push_client_action(user_id, "show_destination", payload)
            return {
                "ok": True,
                "spoken": f"Encontré {label}, señor. Lo marqué en el mapa.",
                "client_action": "show_destination",
                "destination": payload,
            }

        if name in {"stop_navigation", "cancelar_navegacion"}:
            clear_navigation(user_id)
            clear_place_options(user_id)
            vcs.set_map_search_results(user_id, [])
            push_client_action(user_id, "cancel_navigation", {})
            return {
                "ok": True,
                "spoken": "Navegación detenida, señor.",
                "client_action": "cancel_navigation",
            }

        if name in {
            "close_drive",
            "cerrar_mapa",
            "salir_del_mapa",
            "salir_mapa",
            "cerrar_modo_conducir",
        }:
            vcs.set_active_mode(user_id, None)
            vcs.set_map_search_results(user_id, [])
            push_client_action(user_id, "close_drive", {})
            return {
                "ok": True,
                "spoken": "Cierro el mapa, señor.",
                "client_action": "close_drive",
            }

        if name in {"navigation_status", "estado_navegacion", "next_instruction"}:
            route = get_route(user_id)
            if not route:
                options = get_place_options(user_id)
                if options:
                    return _spoken_ok(
                        "Hay destinos en pantalla, señor. Diga cuál prefiere o toque "
                        "Iniciar viaje."
                    )
                return _spoken_ok("No hay ruta activa en este momento, señor.")
            steps = route.get("steps") or []
            idx = min(get_current_step_index(user_id), max(0, len(steps) - 1))
            active = steps[idx] if steps else {}
            instr = str(active.get("instruction") or "Continúe por la ruta").strip()
            return _spoken_ok(
                f"Ruta hacia {route.get('destination', {}).get('label', 'su destino')}. "
                f"Quedan {route.get('duration_text', '')} ({route.get('distance_text', '')}). "
                f"Próximo paso: {instr}, señor."
            )

        return _spoken_err(f"Herramienta no reconocida: {name}", error="unknown_tool")

    except Exception as exc:  # noqa: BLE001
        logger.exception("[VOICE_TOOL] %s failed for user=%s", name, user_id[:8])
        camera_tools = {
            "request_camera_activation",
            "request_camera_deactivation",
            "analyze_camera_frame",
            "buscar_lo_visible",
        }
        if name in camera_tools and vcs.is_camera_active(user_id):
            logger.info(
                "[CAMERA] recovered after exception user=%s tool=%s stream=live",
                user_id[:8],
                name,
            )
            if name == "request_camera_deactivation":
                return _spoken_ok("Cámara desactivada, señor.")
            return _spoken_ok("Cámara activa, señor. ¿Qué desea que analice?")
        return _spoken_err("Lamentablemente hubo un error, señor.", error=str(exc))
