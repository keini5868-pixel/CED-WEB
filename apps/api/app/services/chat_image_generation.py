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
    from app.services.publish_image_context import get_session_vision_analysis

    parts: list[str] = []
    vision = get_session_vision_analysis(user_id, conversation_id)
    if not vision:
        vision = extract_vision_context_from_history(history)
    if vision:
        parts.append(
            "Análisis previo de la imagen de referencia (respeta textos, precios y diseño visibles):\n"
            f"{vision}"
        )
    recent = _recent_chat_context(history or [])
    if recent:
        parts.append(f"Contexto reciente del chat:\n{recent[:2200]}")
    clean = (user_text or "").strip()
    if clean:
        parts.append(f"Instrucciones actuales del usuario (obligatorias):\n{clean}")
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
    from app.services.publish_image_context import (
        has_publishable_image,
        resolve_reference_image_bytes,
    )

    if not resolve_reference_image_bytes(user_id, conversation_id):
        return False
    if user_requests_prior_reference(text):
        return True
    if is_image_creation_request(text, history):
        return True
    if parse_followup_image_prompt(text, history):
        return True
    if has_publishable_image(user_id, conversation_id) and extract_vision_context_from_history(history):
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
    if err.lower().startswith("no pude generar la imagen"):
        return err
    return f"No pude generar la imagen: {err}"


def _append_user_instructions(prompt: str, user_text: str) -> str:
    clean = (user_text or "").strip()
    if not clean or clean in prompt:
        return prompt
    return (
        f"{prompt.rstrip()}\n\n"
        f"Instrucciones adicionales del usuario (obligatorias, incluir textos exactos): {clean[:900]}"
    )[:3800]


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

    user_text = (text or "").strip()
    effective = effective_user_prompt(user_text, history)
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
        model_prompt = _append_user_instructions(creation["internal_prompt"], user_text)
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
            ref_prompt = (
                f"Genera un creativo fiel a la imagen de referencia adjunta. "
                f"{enriched_context[:3200]}"
            )
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
    elif creation:
        logger.info("[CHAT:IMG-GEN] creative brief without bytes user=%s", user_id[:8])
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=model_prompt,
            quality="auto",
            context=enriched_context,
            display_label=display_label,
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
            "url": None,
            "display_label": display_label,
        }

    url = str(img_result["url"])
    if conversation_id:
        register_text_chat_image_url(user_id, conversation_id, url)

    caption = str(img_result.get("caption") or display_label or "Imagen generada")
    from app.services.copy_quality import with_image_text_disclaimer

    reply = with_image_text_disclaimer(
        str(success_reply),
        user_text or model_prompt,
        enriched_context or "",
    )
    return {
        "ok": True,
        "url": url,
        "reply": reply,
        "caption": caption,
        "quality": str(img_result.get("quality") or ""),
        "display_label": display_label,
        "used_reference": bool(ref_payload),
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
