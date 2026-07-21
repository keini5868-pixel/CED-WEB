"""Generación de imágenes en chat (texto y modo avanzado) — capa compartida."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.services.chat_intents import (
    is_casual_chat_interrupt,
    is_generate_image_intent,
    is_pdf_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
    user_requests_prior_reference,
    wants_image_reference_edit,
)
from app.services.marketing_creative import (
    build_display_label,
    extract_product_subject,
    is_image_creation_request,
    is_marketing_creative_intent,
    resolve_image_creation_from_text,
    strip_creative_user_noise,
)

DIRECT_IMAGE_MAX_CHARS = 500

logger = logging.getLogger(__name__)

_VISION_ANALYSIS_MARKERS = (
    "**Qué es**",
    "**Detalle visible**",
    "Qué es —",
    "**Contexto**",
    "**Observaciones**",
)


def extract_vision_context_from_history(history: list[dict[str, str]] | None) -> str:
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in ("assistant", "model"):
            continue
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if any(marker in content for marker in _VISION_ANALYSIS_MARKERS):
            return content[:3500]
    return ""


def _recent_chat_context(history: list[dict[str, str]], *, limit: int = 8) -> str:
    chunks: list[str] = []
    for row in (history or [])[-limit:]:
        content = (row.get("content") or "").strip()
        if content:
            chunks.append(content)
    return " ".join(chunks)


def build_enriched_generation_context(
    user_text: str,
    history: list[dict[str, str]] | None,
    *,
    user_id: str,
    conversation_id: str | None,
) -> str:
    """Hechos visuales del historial/visión — sin etiquetas meta que Gemini pinte en la foto.

    El pedido actual del usuario va en `prompt`, no aquí. Duplicarlo con
    «Instrucciones actuales del usuario…» hacía que el modelo lo dibujara como tipografía.
    """
    from app.services.publish_image_context import get_session_vision_analysis

    parts: list[str] = []
    vision = get_session_vision_analysis(user_id, conversation_id)
    if not vision:
        vision = extract_vision_context_from_history(history)
    if vision:
        parts.append(vision[:3500])
    recent = _recent_chat_context(history or [])
    if recent:
        # Evita reinyectar el mismo pedido del usuario como “contexto”.
        clean = (user_text or "").strip()
        if clean and clean in recent:
            recent = recent.replace(clean, " ").strip()
        if recent:
            parts.append(recent[:2200])
    return "\n\n".join(parts)[:4000]


def effective_user_prompt(text: str, history: list[dict[str, str]] | None) -> str:
    t = (text or "").strip()
    parsed = parse_generate_image_prompt(t)
    if parsed:
        return parsed
    followup = parse_followup_image_prompt(t, history)
    if followup:
        return followup
    cleaned = strip_creative_user_noise(t)
    return cleaned or t


def should_use_reference_generation(
    text: str,
    history: list[dict[str, str]] | None,
    *,
    user_id: str,
    conversation_id: str | None,
) -> bool:
    """Solo ruta con referencia si el pedido lo pide de forma explícita.

    Tener bytes de imagen en sesión (p.ej. tras analizar o tras un edit fallido)
    NO debe forzar generate_image_with_reference en un «genera una imagen de X»
    plano: eso dejaba el chat atascado en el path de referencia tras un fallo.
    """
    from app.services.publish_image_context import resolve_reference_image_bytes

    if not resolve_reference_image_bytes(user_id, conversation_id):
        return False
    # Variación / edición / «igual a la que te pasé» / «mismos precios».
    if wants_image_reference_edit(text):
        return True
    # Follow-up corto que continúa editando el hilo visual.
    if parse_followup_image_prompt(text, history):
        return True
    # Flyer/creativo/banner: suele querer la foto de producto ya subida.
    if is_marketing_creative_intent(text):
        return True
    return False


def should_take_direct_image_path(
    text: str,
    history: list[dict[str, str]] | None,
) -> bool:
    t = (text or "").strip()
    if not t or is_casual_chat_interrupt(t) or is_pdf_intent(t):
        return False
    if len(t) > DIRECT_IMAGE_MAX_CHARS:
        return False
    if is_generate_image_intent(t):
        return True
    if parse_followup_image_prompt(t, history):
        return True
    if is_image_creation_request(t, history):
        return True
    return False


def _format_error(raw_error: str) -> str:
    err = (raw_error or "").strip() or "No pude generar la imagen."
    if "no devolvió imagen" in err.lower():
        # Gemini no devolvió imagen tras varios intentos/modelos sin excepción ni
        # motivo explícito. Dos causas típicas: (a) personajes/marcas con derechos
        # de autor (Marvel, DC, etc.) bloqueados por el filtro de contenido, o
        # (b) un límite temporal de la API. No hubo imagen generada en ningún caso;
        # decirlo con honestidad y sin afirmar la causa como certeza (antes se
        # aseguraba "es por copyright", lo cual es engañoso si en realidad fue un
        # límite temporal — y también engañoso el hint genérico de "sea más
        # concreto", porque el problema no es vaguedad del pedido).
        return (
            "No pude generar la imagen: no se generó ninguna imagen. Puede ser que el "
            "sistema bloqueara el pedido — por ejemplo si describe un personaje o marca "
            "con derechos de autor protegidos — o un límite temporal del servicio. "
            "Puedo intentarlo de nuevo, o si es un personaje con marca registrada, "
            "puedo crear algo similar sin usar esa marca específica."
        )
    if err.lower().startswith("no pude generar la imagen"):
        return err
    return f"No pude generar la imagen: {err}"


def _merge_creative_user_request(prompt: str, user_text: str) -> str:
    """Añade el pedido del usuario al brief creativo sin etiquetas meta pintables."""
    from app.services.gemini_images import strip_image_generation_instruction, strip_image_prompt_meta

    clean = strip_image_prompt_meta(strip_image_generation_instruction(user_text or ""))
    base = strip_image_prompt_meta((prompt or "").strip())
    if not clean or clean.lower() in base.lower():
        return base[:3800]
    return f"{base.rstrip()}\n\nPedido visual del usuario: {clean[:900]}"[:3800]

def run_chat_image_generation(
    user_id: str,
    conversation_id: str | None,
    text: str,
    history: list[dict[str, str]] | None,
    *,
    plan_id: str | None = None,
    allow_reference: bool = True,
) -> dict[str, Any]:
    """
    Ejecuta generación de imagen para chat. Nunca devuelve ok=True sin url.

    allow_reference=False: solo descripción de texto (voz v1 — sin imagen de referencia).
    """
    from app.services.gemini_images import generate_image
    from app.services.image_reference_generator import generate_image_with_reference
    from app.services.publish_image_context import (
        register_text_chat_image_url,
        resolve_reference_image_bytes,
    )

    from app.services.copy_quality import prompt_requires_ideogram_text

    user_text = (text or "").strip()
    effective = effective_user_prompt(user_text, history)
    # Señal ESTRICTA (comillas explícitas o "que diga/ponga X") tomada solo del pedido
    # ACTUAL del usuario — decide si intentar Ideogram (texto legible) antes de Gemini.
    # Ideogram no aplica a ediciones sobre imagen de referencia (ver ref_payload abajo).
    wants_literal_text = prompt_requires_ideogram_text(user_text)
    enriched_context = build_enriched_generation_context(
        user_text,
        history,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    use_reference = allow_reference and should_use_reference_generation(
        user_text,
        history,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    ref_payload = resolve_reference_image_bytes(user_id, conversation_id) if use_reference else None

    creation = resolve_image_creation_from_text(
        user_text,
        history,
        has_reference_image=bool(ref_payload),
    )
    display_label = ""
    success_reply = "Listo. Aquí está tu imagen generada."
    style_mode = "edit"

    if creation:
        display_label = creation["display_label"]
        success_reply = creation.get("reply") or "Listo. Aquí está su creativo."
        style_mode = creation.get("style_mode") or "edit"
        model_prompt = _merge_creative_user_request(creation["internal_prompt"], user_text)
    else:
        chat_context = _recent_chat_context(history or [])
        if is_marketing_creative_intent(user_text):
            display_label = build_display_label(extract_product_subject(chat_context))
            success_reply = "Listo, señor. Aquí está su creativo publicitario."
        model_prompt = effective

    img_result: dict[str, Any]

    if ref_payload:
        ref_bytes, ref_mime = ref_payload
        ref_prompt = model_prompt
        if not creation:
            # Pedido visual + hechos de visión/historial — sin wrappers «Instrucciones…».
            bits = [effective]
            if enriched_context:
                bits.append(enriched_context[:2000])
            ref_prompt = "\n\n".join(b for b in bits if b).strip()
        logger.info(
            "[CHAT:IMG-GEN] reference path user=%s bytes=%s conv=%s",
            user_id[:8],
            len(ref_bytes),
            (conversation_id or "")[:8],
        )
        img_result = generate_image_with_reference(
            user_id=user_id,
            prompt=ref_prompt,
            reference_image=ref_bytes,
            content_type=ref_mime,
            style_mode=style_mode if creation else "edit",
            quality="auto",
        )
        # Aislamiento: si el path de referencia falla y el pedido NO era edit/variación
        # explícito, reintentar como generación plana para no tumbar el chat.
        if (not img_result.get("ok") or not img_result.get("url")) and not wants_image_reference_edit(
            user_text
        ):
            logger.warning(
                "[CHAT:IMG-GEN] reference failed; falling back to plain user=%s code=%s",
                user_id[:8],
                img_result.get("code"),
            )
            img_result = generate_image(
                user_id=user_id,
                plan_id=plan_id,
                prompt=model_prompt,
                quality="auto",
                context=enriched_context or _recent_chat_context(history or []),
                display_label=display_label or None,
                prefer_ideogram=wants_literal_text,
            )
            ref_payload = None
    elif creation:
        logger.info("[CHAT:IMG-GEN] creative brief without bytes user=%s", user_id[:8])
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=model_prompt,
            quality="auto",
            context=enriched_context,
            display_label=display_label,
            prefer_ideogram=wants_literal_text,
        )
    else:
        logger.info("[CHAT:IMG-GEN] plain generate user=%s", user_id[:8])
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=model_prompt,
            quality="auto",
            context=enriched_context or _recent_chat_context(history or []),
            display_label=display_label or None,
            prefer_ideogram=wants_literal_text,
        )

    if not img_result.get("ok") or not img_result.get("url"):
        err = _format_error(str(img_result.get("error") or "No pude generar la imagen."))
        logger.warning(
            "[CHAT:IMG-GEN] failed user=%s code=%s ref=%s",
            user_id[:8],
            img_result.get("code"),
            bool(ref_payload),
        )
        return {
            "ok": False,
            "error": err,
            "reply": err,
            "code": img_result.get("code"),
            "url": None,
            "display_label": display_label,
        }

    url = str(img_result["url"])
    if conversation_id:
        register_text_chat_image_url(user_id, conversation_id, url)

    caption = str(img_result.get("caption") or display_label or "Imagen generada")

    if img_result.get("ideogram_used"):
        # Ideogram ya renderiza texto legible — el aviso de "texto puede salir mal"
        # (pensado para Gemini) no aplica y solo generaría desconfianza injustificada.
        reply = str(success_reply)
    else:
        from app.services.copy_quality import with_image_text_disclaimer

        reply = with_image_text_disclaimer(
            str(success_reply),
            user_text or model_prompt,
            enriched_context or "",
        )
        if img_result.get("ideogram_declined_reason") == "basic_excluded":
            reply = (
                f"{reply}\n\nCon un plan de pago (desde Starter) puedo usar un motor "
                "especializado en texto (Ideogram) para que se vea más legible, señor."
            )

    return {
        "ok": True,
        "url": url,
        "reply": reply,
        "caption": caption,
        "quality": str(img_result.get("quality") or ""),
        "display_label": display_label,
        "used_reference": bool(ref_payload),
        "provider": img_result.get("provider"),
    }


_HALLUCINATED_GENERATE_IMAGE = re.compile(r"generate_image\s*\(", re.I)
_HALLUCINATED_JSON_PROMPT = re.compile(
    r"""generate_image\s*\(\s*\{[^}]*["']prompt["']\s*:\s*["']([^"']+)["']""",
    re.I | re.S,
)
_HALLUCINATED_KW_PROMPT = re.compile(
    r"""generate_image\s*\(\s*prompt\s*=\s*["']([^"']+)["']""",
    re.I,
)
_FALSE_SUCCESS_MARKERS = (
    "aquí está tu",
    "aqui esta tu",
    "here is your",
    "here's your",
    "here is the",
    "listo, señor",
    "listo senor",
)
_VISUAL_NOUNS = (
    "imagen",
    "foto",
    "árbol",
    "arbol",
    "tree",
    "creativo",
    "picture",
    "image",
    "photo",
    "flyer",
)


def looks_like_hallucinated_generate_image(text: str) -> bool:
    return bool(_HALLUCINATED_GENERATE_IMAGE.search(text or ""))


def extract_hallucinated_generate_image_prompt(text: str) -> str | None:
    blob = text or ""
    match = _HALLUCINATED_JSON_PROMPT.search(blob)
    if match:
        return match.group(1).strip()
    match = _HALLUCINATED_KW_PROMPT.search(blob)
    if match:
        return match.group(1).strip()
    return None


def strip_hallucinated_generate_image_text(text: str) -> str:
    cleaned = re.sub(
        r"print\s*\(\s*generate_image\s*\([^)]*\)\s*\)",
        "",
        text or "",
        flags=re.I | re.S,
    )
    cleaned = re.sub(
        r"generate_image\s*\(\s*\{.*?\}\s*\)",
        "",
        cleaned,
        flags=re.I | re.S,
    )
    cleaned = re.sub(r"generate_image\s*\([^)]*\)", "", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def reply_promises_image_without_attachment(text: str) -> bool:
    if looks_like_hallucinated_generate_image(text):
        return True
    lowered = (text or "").lower()
    if not lowered:
        return False
    if not any(marker in lowered for marker in _FALSE_SUCCESS_MARKERS):
        return False
    return any(noun in lowered for noun in _VISUAL_NOUNS)


def salvage_image_turn(
    user_id: str,
    conversation_id: str | None,
    user_text: str,
    history: list[dict[str, str]] | None,
    reply: str,
    image_attachment: dict[str, Any] | None,
    *,
    plan_id: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """
    Si el LLM alucinó generate_image(...) o prometió imagen sin adjuntarla,
    ejecuta la generación real o devuelve error claro (nunca texto crudo de tool).
    """
    if image_attachment and image_attachment.get("url"):
        if looks_like_hallucinated_generate_image(reply):
            clean = strip_hallucinated_generate_image_text(reply)
            return clean or str(image_attachment.get("caption") or "Imagen generada"), image_attachment
        return reply, image_attachment

    wants_image = should_take_direct_image_path(user_text, history)
    hallucinated = looks_like_hallucinated_generate_image(reply)
    false_success = reply_promises_image_without_attachment(reply)
    if not wants_image and not hallucinated and not false_success:
        return reply, image_attachment

    logger.warning(
        "[CHAT:IMG-GEN] salvage turn user=%s wants=%s halluc=%s false_ok=%s",
        user_id[:8],
        wants_image,
        hallucinated,
        false_success,
    )
    gen = run_chat_image_generation(
        user_id,
        conversation_id,
        user_text,
        history,
        plan_id=plan_id,
    )
    if gen.get("ok") and gen.get("url"):
        clean = strip_hallucinated_generate_image_text(reply)
        if not clean or false_success or hallucinated:
            clean = str(gen.get("reply") or "Listo. Aquí está tu imagen generada.")
        attachment = {
            "url": str(gen["url"]),
            "caption": str(gen.get("caption") or "Imagen generada"),
            "prompt": str(gen.get("caption") or user_text)[:200],
            "quality": gen.get("quality"),
        }
        return clean, attachment

    err = str(gen.get("error") or gen.get("reply") or "No pude generar la imagen.")
    clean = strip_hallucinated_generate_image_text(reply)
    if clean and not hallucinated and not false_success:
        return f"{clean}\n\n{err}", None
    return err, None
