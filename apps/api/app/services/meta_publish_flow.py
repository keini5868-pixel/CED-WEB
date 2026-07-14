"""Publicación Meta (FB/IG) con confirmación — piloto Retell nativo."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any, Literal

from app.services import voice_client_session as vcs
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.publish_text import (
    detect_publish_platform,
    extract_caption_from_turn,
    is_publish_confirm,
    sanitize_publish_caption,
    validate_caption,
)

logger = logging.getLogger(__name__)

META_PUBLISH_TTL_SEC = 600
DraftStatus = Literal["pending", "publishing", "published", "cancelled"]
Platform = Literal["facebook", "instagram"]

_PUBLISH_CANCEL = re.compile(
    r"\b("
    r"no\s*,?\s*(?:public(?:ues|ar)|lo\s+hagas)?|"
    r"cancela(?:r)?|olv[ií]dalo|olvidalo|mejor\s+no|"
    r"no\s+lo\s+publiqu?es|detente|para"
    r")\b",
    re.I,
)


def is_publish_cancel(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_PUBLISH_CANCEL.search(t))


def _idempotency_key(user_id: str, draft_id: str) -> str:
    return hashlib.sha256(f"{user_id}:{draft_id}".encode()).hexdigest()


def _caption_preview(caption: str, limit: int = 120) -> str:
    text = " ".join((caption or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _not_connected_message() -> str:
    return (
        "Señor, Meta no está conectado. "
        "Use Conectar Redes en el panel y acepte todos los permisos de Facebook e Instagram."
    )


def _reconnect_message() -> str:
    return (
        "Señor, falta reconectar Meta con permisos de publicación. "
        "Use Conectar Redes, acepte pages_manage_posts e instagram_content_publish, e intente de nuevo."
    )


def _transcript_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    call = payload.get("call") or {}
    obj = call.get("transcript_object") or call.get("transcriptObject") or []
    return obj if isinstance(obj, list) else []


def _latest_user_utterance(payload: dict[str, Any]) -> str:
    call = payload.get("call") or {}
    transcript_obj = call.get("transcript_object") or call.get("transcriptObject") or []
    if isinstance(transcript_obj, list):
        for entry in reversed(transcript_obj):
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").lower()
            if role in {"user", "customer"}:
                content = str(entry.get("content") or entry.get("text") or "").strip()
                if content:
                    return content
    return ""


def _meta_connected(user_id: str) -> bool:
    from app.services import supabase_db

    conn = supabase_db.get_meta_connection(user_id)
    return bool(conn and conn.get("access_token"))


def prepare_meta_publish(
    user_id: str,
    *,
    call_id: str,
    platform: str = "",
    caption: str = "",
    query: str = "",
) -> dict[str, Any]:
    """Crea borrador de publicación — nunca publica."""
    if not _meta_connected(user_id):
        return {
            "ok": False,
            "status": "not_connected",
            "spoken": _not_connected_message(),
        }

    text = " ".join(filter(None, [query, caption, platform])).strip()
    plat = (platform or "").strip().lower()
    if plat in {"fb", "face"}:
        plat = "facebook"
    if plat in {"ig", "insta"}:
        plat = "instagram"
    if plat not in {"facebook", "instagram"}:
        detected = detect_publish_platform(text or query or caption, default="")
        plat = detected if detected in {"facebook", "instagram"} else ""

    if not plat:
        return {
            "ok": False,
            "status": "needs_platform",
            "spoken": "Señor, ¿publicamos en Facebook o en Instagram?",
        }

    raw_caption = (caption or "").strip() or extract_caption_from_turn(
        query or text, platform=plat
    )
    cleaned = sanitize_publish_caption(raw_caption)
    ok_cap, reason = validate_caption(cleaned)
    if not ok_cap or not cleaned:
        return {
            "ok": False,
            "status": "needs_caption",
            "spoken": (
                "Señor, ¿qué texto desea publicar? "
                "Diga por ejemplo «publica en Facebook que diga Oferta especial hoy»."
            ),
            "reason": reason,
        }

    if plat == "instagram":
        img = vcs.get_last_publishable_image(user_id, ignore_call_binding=True)
        if not img:
            return {
                "ok": False,
                "status": "needs_image",
                "spoken": (
                    "Señor, Instagram requiere una imagen. "
                    "Active la cámara, muestre el producto, o genere/suba una imagen "
                    "y luego diga el texto a publicar."
                ),
            }

    draft_id = str(uuid.uuid4())
    draft = {
        "draft_id": draft_id,
        "call_id": (call_id or "").strip(),
        "platform": plat,
        "caption": cleaned,
        "status": "pending",
        "idempotency_key": _idempotency_key(user_id, draft_id),
        "post_id": None,
    }
    vcs.set_meta_pending_publish(user_id, draft)
    preview = _caption_preview(cleaned)
    label = "Facebook" if plat == "facebook" else "Instagram"
    spoken = (
        f"Le preparo una publicación en {label} que dice: «{preview}». "
        f"¿Confirma que la publique?"
    )
    return {
        "ok": True,
        "status": "awaiting_confirmation",
        "draft_id": draft_id,
        "platform": plat,
        "caption_preview": preview,
        "spoken": spoken,
        "transition": "transition_to_publish_confirm_pending",
    }


def confirm_meta_publish(
    user_id: str,
    *,
    call_id: str,
    payload: dict[str, Any],
    draft_id: str = "",
) -> dict[str, Any]:
    """Publica solo con confirmación explícita verificada en el transcript."""
    draft = vcs.get_meta_pending_publish(user_id)
    if not draft:
        return {
            "ok": False,
            "status": "no_draft",
            "spoken": "Señor, no tengo una publicación pendiente.",
            "transition": "transition_to_general_assistant",
        }

    wanted = (draft_id or "").strip()
    if wanted and wanted != draft.get("draft_id"):
        return {
            "ok": False,
            "status": "draft_mismatch",
            "spoken": "Señor, ese borrador ya no está activo. ¿Desea preparar la publicación de nuevo?",
            "transition": "transition_to_general_assistant",
        }

    if vcs.is_meta_pending_publish_expired(user_id):
        vcs.clear_meta_pending_publish(user_id, reason="expired")
        return {
            "ok": False,
            "status": "expired",
            "spoken": "Señor, ese borrador expiró. ¿Quiere que lo prepare de nuevo?",
            "transition": "transition_to_general_assistant",
        }

    status = str(draft.get("status") or "")
    if status == "published":
        return {
            "ok": True,
            "status": "already_published",
            "spoken": "Señor, esa publicación ya se envió.",
            "transition": "transition_to_general_assistant",
        }
    if status == "cancelled":
        return {
            "ok": False,
            "status": "cancelled",
            "spoken": "Señor, esa publicación fue cancelada.",
            "transition": "transition_to_general_assistant",
        }
    if status == "publishing":
        return {
            "ok": True,
            "status": "in_progress",
            "spoken": "Señor, la publicación ya está en curso.",
        }

    user_line = _latest_user_utterance(payload)
    if not is_publish_confirm(user_line, allow_short_yes=True):
        return {
            "ok": False,
            "status": "confirm_required",
            "spoken": (
                "Señor, no detecté una confirmación clara. "
                "¿Desea publicar? Diga «sí» o «cancela»."
            ),
        }

    if not vcs.try_mark_meta_pending_publishing(user_id, str(draft.get("draft_id") or "")):
        refreshed = vcs.get_meta_pending_publish(user_id) or {}
        if refreshed.get("status") == "published":
            return {
                "ok": True,
                "status": "already_published",
                "spoken": "Señor, esa publicación ya se envió.",
                "transition": "transition_to_general_assistant",
            }
        return {
            "ok": False,
            "status": "race",
            "spoken": "Señor, hubo un conflicto con el borrador. Intente de nuevo.",
        }

    plat = str(draft.get("platform") or "")
    caption = str(draft.get("caption") or "")
    try:
        if plat == "facebook":
            result = publish_facebook(user_id, caption)
        elif plat == "instagram":
            result = publish_instagram(user_id, caption)
        else:
            vcs.revert_meta_pending_to_pending(user_id)
            return {
                "ok": False,
                "status": "invalid_platform",
                "spoken": "Señor, no reconocí la red social del borrador.",
            }

        post_id = str(result.get("post_id") or "")
        vcs.mark_meta_pending_published(user_id, post_id=post_id)
        spoken = str(result.get("spoken") or "").strip()
        if not spoken:
            label = "Facebook" if plat == "facebook" else "Instagram"
            spoken = f"Señor, publicación enviada a {label}."
        logger.info(
            "[META-PUBLISH] published user=%s platform=%s draft=%s",
            user_id[:8],
            plat,
            str(draft.get("draft_id", ""))[:8],
        )
        return {
            "ok": True,
            "status": "published",
            "post_id": post_id,
            "platform": plat,
            "spoken": spoken,
            "transition": "transition_to_general_assistant",
        }
    except MetaSocialError as exc:
        vcs.revert_meta_pending_to_pending(user_id)
        msg = str(exc)
        lower = msg.lower()
        if "no conectado" in lower or "conectar redes" in lower:
            return {"ok": False, "status": "not_connected", "spoken": _not_connected_message()}
        if "permission" in lower or "oauth" in lower or "token" in lower:
            return {"ok": False, "status": "auth", "spoken": _reconnect_message()}
        logger.warning("[META-PUBLISH] MetaSocialError user=%s: %s", user_id[:8], msg[:200])
        return {
            "ok": False,
            "status": "error",
            "spoken": f"Señor, no pude publicar: {msg[:160]}",
        }
    except Exception:  # noqa: BLE001
        vcs.revert_meta_pending_to_pending(user_id)
        logger.exception("[META-PUBLISH] failed user=%s", user_id[:8])
        return {
            "ok": False,
            "status": "error",
            "spoken": "Señor, no pude completar la publicación en este momento.",
        }


def cancel_meta_publish(
    user_id: str,
    *,
    draft_id: str = "",
    reason: str = "user_cancel",
) -> dict[str, Any]:
    draft = vcs.get_meta_pending_publish(user_id)
    if not draft:
        return {
            "ok": True,
            "status": "no_draft",
            "spoken": "No hay publicación pendiente, señor.",
            "transition": "transition_to_general_assistant",
        }
    wanted = (draft_id or "").strip()
    if wanted and wanted != draft.get("draft_id"):
        return {
            "ok": False,
            "status": "draft_mismatch",
            "spoken": "Señor, ese borrador ya no está activo.",
            "transition": "transition_to_general_assistant",
        }
    if draft.get("status") == "published":
        return {
            "ok": True,
            "status": "already_published",
            "spoken": "Señor, esa publicación ya se envió; no puedo cancelarla.",
            "transition": "transition_to_general_assistant",
        }
    vcs.clear_meta_pending_publish(user_id, reason=reason)
    return {
        "ok": True,
        "status": "cancelled",
        "spoken": "Entendido, señor. No publicaré ese contenido.",
        "transition": "transition_to_general_assistant",
    }


def maybe_clear_meta_pending_on_topic_change(user_id: str, tool_name: str) -> None:
    if tool_name in {
        "meta_prepare_publish",
        "meta_confirm_publish",
        "meta_cancel_publish",
    }:
        return
    if vcs.get_meta_pending_publish(user_id):
        vcs.clear_meta_pending_publish(user_id, reason="topic_change")
        logger.info("[META-PUBLISH] cleared pending user=%s tool=%s", user_id[:8], tool_name)


def clear_meta_pending_for_call(user_id: str, call_id: str) -> None:
    draft = vcs.get_meta_pending_publish(user_id)
    if not draft:
        return
    bound = str(draft.get("call_id") or "").strip()
    if bound and call_id and bound != call_id.strip():
        return
    vcs.clear_meta_pending_publish(user_id, reason="call_ended")
