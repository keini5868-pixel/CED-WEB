"""Flujo conversacional de publicación en chat de texto (Instagram / Facebook)."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from app.services.publish_image_context import (
    begin_publish_flow,
    clear_publish_flow,
    clear_session_image,
    get_publish_flow,
    has_publishable_image,
    update_publish_flow,
)
from app.services.publish_text import (
    detect_publish_platform,
    extract_caption_from_turn,
    extract_inline_publish_caption,
    extract_user_caption_for_publish,
    is_publish_confirm,
    is_publish_help_request,
    is_social_publish_intent,
    wants_publish_now,
)

_PLATFORM_LABEL = {"instagram": "Instagram", "facebook": "Facebook"}


def _publish_turn_is_off_topic(text: str) -> bool:
    """Cierra flujo de publicación si el usuario cambió a investigación o charla larga."""
    from app.services.cognitive_intents import is_web_research_intent, requires_live_web

    t = (text or "").strip()
    if not t:
        return False
    if is_social_publish_intent(t) or wants_publish_now(t) or is_publish_confirm(t):
        return False
    if extract_user_caption_for_publish(t):
        return False
    if requires_live_web(t) or is_web_research_intent(t):
        return True
    if len(t) > 180:
        return True
    return False


def publish_flow_opening(platform: str, *, has_caption: bool = False) -> str:
    label = _PLATFORM_LABEL.get(platform, platform)
    if has_caption:
        return (
            f"Imagen recibida, señor. La publicaré en {label} cuando usted confirme.\n\n"
            f"¿Desea que envíe la publicación ahora, o quiere ajustar el texto?"
        )
    return (
        f"Imagen recibida, señor. ¿Necesita que le ayude con el título y la descripción "
        f"para {label}, o ya tiene su texto listo?"
    )


def start_publish_flow_from_image(
    user_id: str,
    conversation_id: str,
    text: str,
) -> str:
    platform = detect_publish_platform(text)
    inline = extract_inline_publish_caption(text, platform=platform)
    if inline:
        begin_publish_flow(
            user_id,
            conversation_id,
            platform=platform,
            caption_draft=inline,
            stage="awaiting_confirm",
        )
        label = _PLATFORM_LABEL.get(platform, platform)
        return (
            f"Imagen recibida, señor. Publicaré en {label} con este texto:\n\n"
            f"{inline}\n\n"
            f"Cuando esté listo, dígame «envía» o «publica»."
        )
    begin_publish_flow(user_id, conversation_id, platform=platform)
    return publish_flow_opening(platform)


def handle_publish_flow_turn(
    user_id: str,
    conversation_id: str,
    text: str,
    *,
    history: list[dict[str, str]],
    run_tool: Callable[..., str],
    suggest_caption: Callable[[str, str, str], str],
) -> str | None:
    """Devuelve respuesta si el turno pertenece al flujo de publicación; si no, None."""
    flow = get_publish_flow(user_id, conversation_id)
    if flow and has_publishable_image(user_id, conversation_id) and _publish_turn_is_off_topic(text):
        clear_publish_flow(user_id, conversation_id)
        flow = None

    if not flow and is_social_publish_intent(text) and has_publishable_image(user_id, conversation_id):
        platform = detect_publish_platform(text)
        inline = extract_inline_publish_caption(text, platform=platform)
        if inline:
            begin_publish_flow(
                user_id,
                conversation_id,
                platform=platform,
                caption_draft=inline,
                stage="awaiting_confirm",
            )
            label = _PLATFORM_LABEL.get(platform, platform)
            return (
                f"Muy bien, señor. Publicaré en {label} con este texto:\n\n"
                f"{inline}\n\n"
                f"Cuando quiera enviarla, dígame «envía» o «publica»."
            )
        begin_publish_flow(user_id, conversation_id, platform=platform)
        return publish_flow_opening(platform)

    if not flow or not has_publishable_image(user_id, conversation_id):
        return None

    platform = str(flow.get("platform") or "instagram")
    label = _PLATFORM_LABEL.get(platform, platform)
    stage = str(flow.get("stage") or "awaiting_caption_choice")
    caption = str(flow.get("caption_draft") or "").strip()
    user_text = (text or "").strip()

    if stage == "awaiting_caption_choice":
        if is_publish_confirm(user_text, allow_short_yes=True) and caption:
            return _execute_publish(
                user_id,
                conversation_id,
                platform,
                caption,
                run_tool=run_tool,
            )
        if is_publish_help_request(user_text):
            draft = suggest_caption(platform, user_text, history).strip()
            draft = _clean_caption_draft(draft)
            if not draft:
                draft = "Un momento especial — compartido desde CED. #CED #EvoluciónDigital"
            update_publish_flow(
                user_id,
                conversation_id,
                caption_draft=draft,
                stage="awaiting_confirm",
            )
            return (
                f"Con gusto, señor. Le propongo este texto para {label}:\n\n"
                f"{draft}\n\n"
                f"¿Publico así o desea ajustar algo? Cuando esté listo, dígame «envía» o «publica»."
            )
        new_caption = extract_caption_from_turn(user_text, platform=platform)
        if new_caption:
            update_publish_flow(
                user_id,
                conversation_id,
                caption_draft=new_caption,
                stage="awaiting_confirm",
            )
            if wants_publish_now(user_text):
                return _execute_publish(
                    user_id,
                    conversation_id,
                    platform,
                    new_caption,
                    run_tool=run_tool,
                )
            return (
                f"Perfecto, señor. Publicaré en {label} con este texto:\n\n"
                f"{new_caption}\n\n"
                f"Cuando quiera enviarla, dígame «envía» o «publica»."
            )
        if caption:
            return (
                f"Muy bien, señor. Tengo este texto listo:\n\n"
                f"{caption}\n\n"
                f"Dígame «envía» o «publica» cuando quiera que lo publique en {label}."
            )
        return (
            f"Disculpe, señor, no entendí el texto. ¿Me lo repite? "
            f"O dígame si desea que le sugiera un título y descripción."
        )

    if stage == "awaiting_confirm":
        new_caption = extract_caption_from_turn(user_text, platform=platform)
        if new_caption:
            caption = new_caption
            update_publish_flow(user_id, conversation_id, caption_draft=caption)

        if wants_publish_now(user_text) or is_publish_confirm(user_text, allow_short_yes=True):
            if caption:
                return _execute_publish(
                    user_id,
                    conversation_id,
                    platform,
                    caption,
                    run_tool=run_tool,
                )
            update_publish_flow(user_id, conversation_id, stage="awaiting_caption_choice")
            return publish_flow_opening(platform)

        if is_publish_help_request(user_text):
            draft = suggest_caption(platform, user_text, history).strip()
            draft = _clean_caption_draft(draft)
            if draft:
                update_publish_flow(user_id, conversation_id, caption_draft=draft)
                return (
                    f"Le propongo este texto actualizado:\n\n"
                    f"{draft}\n\n"
                    f"¿Envío la publicación o desea otro ajuste?"
                )
        if caption:
            return (
                f"Muy bien, señor. Tengo este texto listo:\n\n"
                f"{caption}\n\n"
                f"Dígame «envía» o «publica» cuando quiera que lo publique en {label}."
            )
        update_publish_flow(user_id, conversation_id, stage="awaiting_caption_choice")
        return publish_flow_opening(platform)

    return None


def _clean_caption_draft(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^[-*_\s]+", "", cleaned)
    cleaned = re.sub(r"^(?:aquí tienes|claro|por supuesto)[^.!?]*[.:]\s*", "", cleaned, flags=re.I)
    cleaned = cleaned.strip("*_ ")
    if len(cleaned) < 8:
        return ""
    if cleaned in ("...", "…", "**", "---"):
        return ""
    return cleaned


def _execute_publish(
    user_id: str,
    conversation_id: str,
    platform: str,
    caption: str,
    *,
    run_tool: Callable[..., str],
) -> str:
    label = _PLATFORM_LABEL.get(platform, platform)
    tool_name = "publicar_instagram" if platform == "instagram" else "publicar_facebook"
    payload: dict[str, Any] = {
        "use_last_uploaded_image": True,
    }
    if platform == "instagram":
        payload["caption"] = caption
    else:
        payload["message"] = caption

    raw = run_tool(user_id, tool_name, payload, conversation_id=conversation_id)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"ok": False, "error": "respuesta inválida"}

    clear_publish_flow(user_id, conversation_id)
    if data.get("ok"):
        clear_session_image(user_id, conversation_id)
        return f"Un momento, señor…\n\nListo. Publicación enviada a {label}."
    err = str(data.get("error") or data.get("message") or "No pude completar la publicación.")
    return f"No pude publicar en {label}, señor. {err}"
