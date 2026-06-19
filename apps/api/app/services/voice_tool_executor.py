"""Ejecutor server-side de tools de voz — usado por Retell webhooks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.claude_deep_analysis import consultar_sistema_avanzado
from app.services.cognitive_memory import save_memory, search_memory
from app.services.conversation_memory import (
    format_recall_for_voice,
    recall_previous_conversations,
    save_long_term_memory,
)
from app.services.gemini_grounded import fetch_voice_brief
from app.services.voice_spoken import fit_voice_spoken
from app.services.internal_knowledge import format_hits_for_prompt, search_internal_knowledge
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.navigation_maps import compute_route, geocode_address
from app.services.navigation_session import (
    clear_navigation,
    get_location,
    get_route,
    push_client_action,
    set_route,
)
from app.services.openai_images import generate_image
from app.services.pdf_report import store_pdf
from app.services.prospection import get_prospection_report, set_prospection_enabled
from app.services.social_comments import fetch_social_comments
from app.services.user_address import sync_address_from_memory_key
from app.services import voice_client_session as vcs
from app.services.voice_usage import voice_access_state

logger = logging.getLogger(__name__)


async def _wait_camera_active(user_id: str, timeout_sec: float = 8.0) -> bool:
    import time

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if vcs.is_camera_active(user_id):
            return True
        await asyncio.sleep(0.35)
    return False


async def _wait_vision_result(user_id: str, request_id: int, timeout_sec: float = 16.0) -> str | None:
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
    if not vcs.is_camera_active(user_id):
        vcs.push_client_action(user_id, "camera_activate", {})
        await _wait_camera_active(user_id, 5.0)

    vcs.push_client_action(
        user_id,
        "camera_capture",
        {"request_id": request_id, "question": question, "mode": mode},
    )
    summary = await _wait_vision_result(user_id, request_id)
    if summary:
        return _spoken_ok(summary)
    return _spoken_err(
        "No pude ver la cámara, señor. Verifique que esté encendida en el panel de voz "
        "y que el navegador tenga permiso.",
        error="camera_capture_timeout",
    )


def _spoken_ok(text: str) -> dict[str, Any]:
    return {"ok": True, "spoken": fit_voice_spoken(text)}


def _spoken_err(text: str, *, error: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "spoken": text}
    if error:
        out["error"] = error
    return out


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
            from app.services.cognitive_intents import is_internal_knowledge_query, requires_live_web

            if is_internal_knowledge_query(query) or (
                not requires_live_web(query) and kind == "general"
            ):
                hits = search_internal_knowledge(query, limit=2)
                if hits:
                    internal = format_hits_for_prompt(hits)
                    return _spoken_ok(internal)
                return _spoken_ok(
                    "Con gusto, señor. Puedo explicarle eso con lo que ya tengo en mi cerebro interno."
                )
            result = await asyncio.to_thread(fetch_voice_brief, query, kind=kind)
            if result.get("ok"):
                summary = str(result.get("summary") or "").strip()
                return _spoken_ok(summary if summary else "Consulta completada, señor.")
            return _spoken_err(
                f"No fue posible consultar, señor. {result.get('error', '')}".strip(),
                error=str(result.get("error") or "search_failed"),
            )

        if name == "consultar_claude":
            prompt = str(params.get("prompt") or "").strip()
            result = await asyncio.to_thread(consultar_sistema_avanzado, prompt)
            if result.get("ok"):
                text = str(result.get("result") or "").strip()
                return _spoken_ok(text if text else "Análisis completado, señor.")
            return _spoken_err(
                f"No fue posible el análisis, señor. {result.get('error', '')}".strip(),
                error=str(result.get("error") or "analysis_failed"),
            )

        if name == "generate_image":
            prompt = str(params.get("prompt") or "").strip()
            quality = str(params.get("quality") or "auto")
            balance = voice_access_state(user_id)
            result = await asyncio.to_thread(
                generate_image,
                user_id=user_id,
                plan_id=str(balance.get("plan_id") or ""),
                prompt=prompt,
                quality=quality,
            )
            if result.get("ok"):
                return {
                    "ok": True,
                    "spoken": "Imagen generada, señor.",
                    "url": result.get("url"),
                }
            return _spoken_err(
                f"No fue posible generar la imagen, señor. {result.get('error', '')}".strip(),
                error=str(result.get("error") or "image_failed"),
            )

        if name == "generate_image_with_reference":
            return _spoken_err(
                "Para imágenes con referencia use el chat o la cámara, señor.",
                error="client_reference_required",
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
                vcs.set_camera_active(user_id, False)
                return _spoken_ok("Cámara desactivada, señor.")
            if vcs.is_camera_active(user_id):
                return _spoken_ok("Cámara activa, señor.")
            vcs.push_client_action(user_id, "camera_activate", {})
            if await _wait_camera_active(user_id, 8.0):
                return _spoken_ok("Cámara activa, señor.")
            return _spoken_ok(
                "Encienda la cámara en el panel de voz, señor. "
                "Cuando esté lista, repita qué desea que vea."
            )

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
            titulo = str(params.get("titulo") or "Documento CED").strip()
            contenido = str(params.get("contenido") or titulo).strip()
            artifact = await asyncio.to_thread(
                store_pdf,
                user_id=user_id,
                title=titulo,
                content=contenido,
            )
            return {
                "ok": True,
                "spoken": f"PDF listo, señor. Título: {artifact.title}.",
                "file_id": artifact.file_id,
            }

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

        if name == "activar_prospeccion":
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
            mensaje = str(params.get("mensaje") or "").strip()
            image_url = params.get("image_url")
            image_data = params.get("image_data")
            try:
                result = await asyncio.to_thread(
                    publish_facebook,
                    user_id,
                    mensaje,
                    image_url=str(image_url) if image_url else None,
                    image_data=str(image_data) if image_data else None,
                )
                spoken = str(result.get("spoken") or "Publicación enviada con éxito a Facebook, señor.")
                return _spoken_ok(spoken)
            except MetaSocialError as exc:
                return _spoken_err(f"No fue posible publicar, señor. {exc}")

        if name == "publicar_instagram":
            caption = str(params.get("caption") or "").strip()
            image_url = params.get("image_url")
            image_data = params.get("image_data")
            try:
                result = await asyncio.to_thread(
                    publish_instagram,
                    user_id,
                    caption,
                    image_url=str(image_url) if image_url else None,
                    image_data=str(image_data) if image_data else None,
                )
                spoken = str(result.get("spoken") or "Publicación enviada con éxito a Instagram, señor.")
                return _spoken_ok(spoken)
            except MetaSocialError as exc:
                return _spoken_err(f"No fue posible publicar, señor. {exc}")

        if name == "activar_modo_conducir":
            push_client_action(user_id, "open_drive", {})
            return {
                "ok": True,
                "spoken": "Abriendo el mapa y modo conducir, señor.",
                "client_action": "open_drive",
            }

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

        if name == "iniciar_navegacion":
            destino = str(params.get("destino") or params.get("query") or "").strip()
            if not destino:
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
            route = await asyncio.to_thread(
                compute_route,
                origin_lat=float(loc["lat"]),
                origin_lng=float(loc["lng"]),
                dest_lat=float(geo["lat"]),
                dest_lng=float(loc["lng"]),
                dest_label=str(geo.get("formatted_address") or destino),
            )
            if not route.get("ok"):
                return _spoken_err(
                    str(route.get("error") or "No pude calcular la ruta, señor."),
                    error="route_failed",
                )
            set_route(user_id, route)
            push_client_action(user_id, "apply_route", route)
            spoken = fit_voice_spoken(
                f"Ruta lista, señor. {route.get('duration_text', '')} "
                f"({route.get('distance_text', '')}). Le guiaré paso a paso."
            )
            return {
                "ok": True,
                "spoken": spoken,
                "client_action": "apply_route",
                "route": route,
            }

        if name == "cancelar_navegacion":
            clear_navigation(user_id)
            push_client_action(user_id, "cancel_navigation", {})
            return {
                "ok": True,
                "spoken": "Navegación cancelada, señor.",
                "client_action": "cancel_navigation",
            }

        if name == "estado_navegacion":
            route = get_route(user_id)
            if not route:
                return _spoken_ok("No hay ruta activa en este momento, señor.")
            return _spoken_ok(
                f"Ruta activa hacia {route.get('destination', {}).get('label', 'su destino')}. "
                f"Quedan aproximadamente {route.get('duration_text', '')} "
                f"({route.get('distance_text', '')}), señor."
            )

        return _spoken_err(f"Herramienta no reconocida: {name}", error="unknown_tool")

    except Exception as exc:  # noqa: BLE001
        logger.exception("[VOICE_TOOL] %s failed for user=%s", name, user_id[:8])
        return _spoken_err("Lamentablemente hubo un error, señor.", error=str(exc))
