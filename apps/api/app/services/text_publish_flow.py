"""Flujo conversacional de publicación en chat de texto (Instagram / Facebook)."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from app.services.publish_image_context import (
    begin_publish_flow,
    clear_publish_flow,
    get_publish_flow,
    has_publishable_image,
    update_publish_flow,
)
from app.services.publish_text import (
    detect_publish_platform,
    detect_publish_platform_explicit,
    extract_caption_from_history,
    extract_caption_from_turn,
    extract_initial_publish_caption,
    extract_inline_publish_caption,
    extract_user_caption_for_publish,
    history_awaits_publish_image,
    is_deictic_caption_reference,
    is_image_for_publish_signal,
    is_publish_confirm,
    is_publish_help_request,
    is_social_publish_intent,
    wants_publish_now,
)

_PLATFORM_LABEL = {"instagram": "Instagram", "facebook": "Facebook"}


def _sync_platform_from_user_text(
    user_id: str,
    conversation_id: str,
    user_text: str,
    current_platform: str,
) -> str:
    """Actualiza la red del flujo si el usuario la menciona en este turno."""
    explicit = detect_publish_platform_explicit(user_text)
    if not explicit:
        return current_platform
    if explicit != current_platform:
        update_publish_flow(user_id, conversation_id, platform=explicit)
    return explicit


def _publish_turn_is_off_topic(text: str) -> bool:
    """Cierra flujo de publicación si el usuario cambió a investigación o charla larga."""
    from app.services.cognitive_intents import is_web_research_intent, requires_live_web

    t = (text or "").strip()
    if not t:
        return False
    if is_publish_help_request(t):
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
    label = _PLATFORM_LABEL.get(platform, "")
    if not label:
        if has_caption:
            return (
                "Imagen recibida, señor. La publicaré cuando usted confirme.\n\n"
                "¿Desea publicar en Facebook o Instagram? "
                "¿Envío la publicación ahora o quiere ajustar el texto?"
            )
        return (
            "Imagen recibida, señor. ¿Desea publicar en Facebook o Instagram? "
            "¿Necesita que le ayude con el título y la descripción, o ya tiene su texto listo?"
        )
    if has_caption:
        return (
            f"Imagen recibida, señor. La publicaré en {label} cuando usted confirme.\n\n"
            f"¿Desea que envíe la publicación ahora, o quiere ajustar el texto?"
        )
    return (
        f"Imagen recibida, señor. ¿Necesita que le ayude con el título y la descripción "
        f"para {label}, o ya tiene su texto listo?"
    )


def _resolve_flow_caption(
    user_text: str,
    *,
    platform: str,
    history: list[dict[str, str]],
    existing: str = "",
) -> str:
    """Resuelve caption del turno, del historial o del borrador previo."""
    from app.services.publish_text import sanitize_publish_caption, validate_caption

    cap = extract_caption_from_turn(user_text, platform=platform)
    if cap:
        cleaned = sanitize_publish_caption(cap)
        if validate_caption(cleaned)[0]:
            return cleaned
    if is_deictic_caption_reference(user_text):
        from_history = extract_caption_from_history(history, platform=platform)
        if from_history:
            return from_history
        return existing.strip()
    if existing.strip():
        return existing.strip()
    return extract_caption_from_history(history, platform=platform)


def start_publish_flow_awaiting_image(
    user_id: str,
    conversation_id: str,
    text: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Inicia publicación sin imagen todavía (pedido por texto)."""
    explicit = detect_publish_platform_explicit(text)
    platform = explicit or detect_publish_platform(text) or ""
    inline = (
        extract_initial_publish_caption(text, platform=platform or "facebook")
        or extract_inline_publish_caption(text, platform=platform or "facebook")
    )
    if not inline and history:
        inline = extract_caption_from_history(history, platform=platform or "facebook")
    begin_publish_flow(
        user_id,
        conversation_id,
        platform=platform,
        caption_draft=inline or "",
        stage="awaiting_image",
    )
    label = _PLATFORM_LABEL.get(platform, "")
    if label and inline:
        return (
            f"Perfecto, señor. Publicaré en {label} con este texto:\n\n"
            f"{inline}\n\n"
            f"Ahora adjunte la imagen (o elija «Usar para publicar») y le pido confirmación final."
        )
    if label:
        return (
            f"Muy bien, señor. {label} está listo para publicar. "
            f"Adjunte la imagen que desea usar (botón de adjuntar o «Usar para publicar»)."
        )
    return (
        "Muy bien, señor. Adjunte la imagen para publicar y indíqueme si es Facebook o Instagram."
    )


def continue_publish_after_image(
    user_id: str,
    conversation_id: str,
    text: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Imagen recién registrada + flujo pending / señal de publicar → avanza el borrador."""
    flow = get_publish_flow(user_id, conversation_id)
    explicit = detect_publish_platform_explicit(text)
    platform = (explicit or (str(flow.get("platform") or "") if flow else "") or "").strip()
    # Sin red explícita: dejar vacío para preguntar FB/IG (no forzar default).
    caption = str(flow.get("caption_draft") or "").strip() if flow else ""
    caption = _resolve_flow_caption(
        text,
        platform=platform or "instagram",
        history=history or [],
        existing=caption,
    ) or caption
    if not caption and history:
        caption = extract_caption_from_history(history, platform=platform or "instagram")
    if caption and platform:
        begin_publish_flow(
            user_id,
            conversation_id,
            platform=platform,
            caption_draft=caption,
            stage="awaiting_confirm",
        )
        label = _PLATFORM_LABEL.get(platform, platform)
        return (
            f"Imagen recibida, señor. Publicaré en {label} con este texto:\n\n"
            f"{caption}\n\n"
            f"Cuando esté listo, dígame «envía» o «publica»."
        )
    if caption and not platform:
        begin_publish_flow(
            user_id,
            conversation_id,
            platform="",
            caption_draft=caption,
            stage="awaiting_confirm",
        )
        return (
            "Imagen recibida, señor. La publicaré cuando usted confirme.\n\n"
            f"Texto: {caption}\n\n"
            "¿Desea publicar en Facebook o Instagram? "
            "¿Envío la publicación ahora o quiere ajustar el texto?"
        )
    begin_publish_flow(
        user_id,
        conversation_id,
        platform=platform,
        caption_draft="",
        stage="awaiting_caption_choice",
    )
    return publish_flow_opening(platform)


def start_publish_flow_from_image(
    user_id: str,
    conversation_id: str,
    text: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> str:
    return continue_publish_after_image(
        user_id,
        conversation_id,
        text,
        history=history,
    )


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
    if (
        flow
        and str(flow.get("stage") or "") != "awaiting_image"
        and has_publishable_image(user_id, conversation_id)
        and _publish_turn_is_off_topic(text)
    ):
        clear_publish_flow(user_id, conversation_id)
        flow = None

    # Pedido de publicar SIN imagen → esperar adjunto (no inventar éxito).
    if not flow and is_social_publish_intent(text) and not has_publishable_image(user_id, conversation_id):
        return start_publish_flow_awaiting_image(
            user_id,
            conversation_id,
            text,
            history=history,
        )

    if not flow and is_social_publish_intent(text) and has_publishable_image(user_id, conversation_id):
        explicit = detect_publish_platform_explicit(text)
        platform = explicit or detect_publish_platform(text)
        inline = (
            extract_initial_publish_caption(text, platform=platform)
            or extract_inline_publish_caption(text, platform=platform)
            or extract_caption_from_history(history, platform=platform)
        )
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
        begin_publish_flow(user_id, conversation_id, platform=explicit or "")
        return publish_flow_opening(explicit or "")

    # «esa imagen» con foto ya en contexto + historial de publicar.
    if (
        not flow
        and has_publishable_image(user_id, conversation_id)
        and (
            is_image_for_publish_signal(text)
            or (history_awaits_publish_image(history) and is_image_for_publish_signal(text))
        )
    ):
        return continue_publish_after_image(
            user_id,
            conversation_id,
            text,
            history=history,
        )

    if not flow:
        return None

    platform = str(flow.get("platform") or "").strip()
    user_text = (text or "").strip()
    platform = _sync_platform_from_user_text(user_id, conversation_id, user_text, platform)
    if not platform:
        platform = detect_publish_platform(user_text)
    label = _PLATFORM_LABEL.get(platform, platform)
    stage = str(flow.get("stage") or "awaiting_caption_choice")
    caption = str(flow.get("caption_draft") or "").strip()

    if stage == "awaiting_image":
        if has_publishable_image(user_id, conversation_id):
            return continue_publish_after_image(
                user_id,
                conversation_id,
                user_text,
                history=history,
            )
        # Actualizar caption/plataforma mientras espera la imagen.
        if user_text:
            new_cap = _resolve_flow_caption(
                user_text,
                platform=platform or "facebook",
                history=history,
                existing=caption,
            )
            if new_cap:
                update_publish_flow(
                    user_id,
                    conversation_id,
                    caption_draft=new_cap,
                    platform=platform or None,
                )
                caption = new_cap
            elif explicit := detect_publish_platform_explicit(user_text):
                update_publish_flow(user_id, conversation_id, platform=explicit)
                platform = explicit
                label = _PLATFORM_LABEL.get(platform, platform)
        if label and caption:
            return (
                f"Tengo el texto para {label}, señor. "
                f"Adjunte la imagen (o «Usar para publicar») para continuar."
            )
        if label:
            return (
                f"Todavía necesito la imagen para publicar en {label}, señor. "
                f"Adjúntela con el botón de imagen o elija «Usar para publicar»."
            )
        return (
            "Todavía necesito la imagen para publicar, señor. "
            "Adjúntela cuando esté listo."
        )

    if not has_publishable_image(user_id, conversation_id):
        if stage in {"awaiting_confirm", "awaiting_caption_choice"}:
            update_publish_flow(user_id, conversation_id, stage="awaiting_image")
            return (
                f"No encuentro la imagen del borrador, señor. "
                f"Adjúntela de nuevo para publicar"
                f"{f' en {label}' if label else ''}."
            )
        return None

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
        new_caption = _resolve_flow_caption(
            user_text,
            platform=platform,
            history=history,
            existing=caption,
        )
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
        resolved = _resolve_flow_caption(
            user_text,
            platform=platform,
            history=history,
            existing=caption,
        )
        if resolved:
            caption = resolved
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
    from app.services.copy_quality import polish_spanish_for_user

    cleaned = (text or "").strip()
    cleaned = re.sub(r"^[-*_\s]+", "", cleaned)
    cleaned = re.sub(r"^(?:aquí tienes|claro|por supuesto)[^.!?]*[.:]\s*", "", cleaned, flags=re.I)
    cleaned = cleaned.strip("*_ ")
    if len(cleaned) < 8:
        return ""
    if cleaned in ("...", "…", "**", "---"):
        return ""
    return polish_spanish_for_user(cleaned)


def _execute_publish(
    user_id: str,
    conversation_id: str,
    platform: str,
    caption: str,
    *,
    run_tool: Callable[..., str],
) -> str:
    label = _PLATFORM_LABEL.get(platform, platform)
    if not has_publishable_image(user_id, conversation_id):
        return (
            f"No encuentro la imagen para publicar en {label}, señor. "
            "Adjúntela de nuevo o genere el creativo otra vez."
        )
    from app.services.publish_text import sanitize_publish_caption, validate_caption

    clean_caption = sanitize_publish_caption(caption)
    is_valid, reason = validate_caption(clean_caption)
    if not is_valid:
        return (
            f"El texto para {label} no parece correcto ({reason}). "
            "¿Me indica el caption exacto que desea publicar?"
        )
    tool_name = "publicar_instagram" if platform == "instagram" else "publicar_facebook"
    payload: dict[str, Any] = {
        "use_last_uploaded_image": True,
    }
    if platform == "instagram":
        payload["caption"] = clean_caption
    else:
        payload["message"] = clean_caption

    raw = run_tool(user_id, tool_name, payload, conversation_id=conversation_id)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"ok": False, "error": "respuesta inválida"}

    clear_publish_flow(user_id, conversation_id)
    if data.get("ok"):
        return f"Un momento, señor…\n\nListo. Publicación enviada a {label}."
    err = str(data.get("error") or data.get("message") or "No pude completar la publicación.")
    return f"No pude publicar en {label}, señor. {err}"
