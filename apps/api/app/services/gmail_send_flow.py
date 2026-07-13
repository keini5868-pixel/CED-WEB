"""Flujo Gmail escritura con confirmación — piloto Retell nativo (staging)."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any, Literal

import httpx

from app.services import voice_client_session as vcs
from app.services.google_gmail_api import send_message
from app.services.google_oauth import force_refresh_access_token, get_valid_access_token

logger = logging.getLogger(__name__)

GMAIL_SEND_TTL_SEC = 600
DraftStatus = Literal["pending", "sending", "sent", "cancelled"]

_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}$")

_GMAIL_SEND_CONFIRM = re.compile(
    r"\b("
    r"s[ií]\s*,?\s*(?:env[ií]a(?:lo|la|me|r)?|m[aá]ndalo|mandalo|confirma(?:lo)?)|"
    r"env[ií]a(?:lo|la|me|r)?|m[aá]ndalo|mandalo|"
    r"dale|adelante|de\s+acuerdo|confirmo|confirma(?:do)?|"
    r"procede|hazlo|s[ií]\s+por\s+favor"
    r")\b",
    re.I,
)

_GMAIL_SEND_CANCEL = re.compile(
    r"\b("
    r"no\s*,?\s*(?:env[ií]es|mandes|lo\s+hagas)?|"
    r"cancela(?:r)?|olv[ií]dalo|olvidalo|mejor\s+no|"
    r"no\s+lo\s+env[ií]es|detente|para"
    r")\b",
    re.I,
)

_AGENT_CONFIRM_ASK = re.compile(
    r"\b(confirm(?:o|a|ar|e)?|env[ií]o|env[ií]e|enviar|mand(?:o|e|ar)|"
    r"¿\s*desea|desea\s+que|procedo)\b",
    re.I,
)


def is_gmail_send_confirm(text: str, *, allow_short_yes: bool = False) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if allow_short_yes and re.fullmatch(r"s[ií][\s!.]*", t, re.I):
        return True
    if re.fullmatch(r"s[ií]\s*(?:env[ií]a(?:lo|la)?)[\s!.]*", t, re.I):
        return True
    return bool(_GMAIL_SEND_CONFIRM.search(t))


def is_gmail_send_cancel(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_GMAIL_SEND_CANCEL.search(t))


def _normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _idempotency_key(user_id: str, draft_id: str) -> str:
    raw = f"{user_id}:{draft_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _body_preview(body: str, limit: int = 120) -> str:
    text = " ".join((body or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _agent_recently_asked_confirm(transcript: list[dict[str, Any]]) -> bool:
    """Evita confirmar un 'sí' ambiguo si el agente no acaba de pedir envío."""
    agent_lines: list[str] = []
    for entry in reversed(transcript):
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "").lower()
        content = str(entry.get("content") or entry.get("text") or "").strip()
        if role in {"agent", "assistant"} and content:
            agent_lines.append(content)
            if len(agent_lines) >= 3:
                break
    if not agent_lines:
        return True
    return any(_AGENT_CONFIRM_ASK.search(line) for line in agent_lines)


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
    transcript = str(call.get("transcript") or "").strip()
    if transcript:
        lines = [ln.strip() for ln in transcript.splitlines() if ln.strip()]
        for line in reversed(lines):
            lower = line.lower()
            if lower.startswith("user:"):
                text = line.split(":", 1)[-1].strip()
                if text:
                    return text
    return ""


def _not_connected_message() -> str:
    return (
        "Señor, aún no tiene Gmail conectado. "
        "Use el botón Conectar Gmail en configuración de voz."
    )


def _reconnect_message() -> str:
    return (
        "Señor, Gmail necesita reconexión. "
        "Use el botón Conectar Gmail en configuración de voz e intente de nuevo."
    )


def _gmail_api_call(user_id: str, fn):
    access = get_valid_access_token("gmail", user_id)
    try:
        return fn(access)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403):
            raise
        access = force_refresh_access_token("gmail", user_id)
        return fn(access)


def prepare_gmail_send(
    user_id: str,
    *,
    call_id: str,
    to: str = "",
    subject: str = "",
    body: str = "",
    query: str = "",
) -> dict[str, Any]:
    """Valida campos, crea borrador pending — nunca envía."""
    recipient = _normalize_email(to)
    subj = (subject or "").strip()
    msg_body = (body or "").strip()

    if not recipient and query:
        from app.services.google_gmail_api import extract_recipient

        recipient = _normalize_email(extract_recipient(query))

    if not msg_body and query:
        body_match = re.search(
            r"(?:diciendo|que\s+diga|con\s+el\s+mensaje|dile\s+que)\s+(.+)$",
            query,
            re.I,
        )
        if body_match:
            msg_body = body_match.group(1).strip()
        subj_match = re.search(
            r"(?:asunto|subject)\s+(.+?)(?:,|\s+dile|\s+que\s+diga|\s+diciendo|$)",
            query,
            re.I,
        )
        if subj_match and not subj:
            subj = subj_match.group(1).strip().strip("'\"")

    if not recipient:
        return {
            "ok": False,
            "status": "needs_recipient",
            "spoken": "Señor, ¿a qué correo desea enviar el mensaje?",
        }
    if not _valid_email(recipient):
        return {
            "ok": False,
            "status": "invalid_recipient",
            "spoken": f"Señor, «{recipient}» no parece un correo válido. ¿Cuál es la dirección?",
        }
    if not subj:
        return {
            "ok": False,
            "status": "needs_subject",
            "spoken": "Señor, ¿cuál es el asunto del correo?",
        }
    if not msg_body:
        return {
            "ok": False,
            "status": "needs_body",
            "spoken": "Señor, ¿qué desea decir en el cuerpo del mensaje?",
        }

    draft_id = str(uuid.uuid4())
    draft = {
        "draft_id": draft_id,
        "call_id": (call_id or "").strip(),
        "to": recipient,
        "subject": subj[:200],
        "body": msg_body[:8000],
        "status": "pending",
        "idempotency_key": _idempotency_key(user_id, draft_id),
        "sent_message_id": None,
    }
    vcs.set_gmail_pending_send(user_id, draft)
    preview = _body_preview(msg_body)
    spoken = (
        f"Le preparo un correo para {recipient}, asunto «{subj}», "
        f"que dice: {preview}. ¿Desea que lo envíe?"
    )
    return {
        "ok": True,
        "status": "awaiting_confirmation",
        "draft_id": draft_id,
        "to": recipient,
        "subject": subj,
        "body_preview": preview,
        "spoken": spoken,
        "transition": "transition_to_gmail_confirm_pending",
    }


def confirm_gmail_send(
    user_id: str,
    *,
    call_id: str,
    payload: dict[str, Any],
    draft_id: str = "",
) -> dict[str, Any]:
    """Envía solo con confirmación explícita verificada en el transcript."""
    draft = vcs.get_gmail_pending_send(user_id)
    if not draft:
        return {
            "ok": False,
            "status": "no_draft",
            "spoken": "Señor, no tengo un correo pendiente de envío.",
            "transition": "transition_to_general_assistant",
        }

    wanted = (draft_id or "").strip()
    if wanted and wanted != draft.get("draft_id"):
        return {
            "ok": False,
            "status": "draft_mismatch",
            "spoken": "Señor, ese borrador ya no está activo. ¿Desea preparar el correo de nuevo?",
            "transition": "transition_to_general_assistant",
        }

    if vcs.is_gmail_pending_send_expired(user_id):
        vcs.clear_gmail_pending_send(user_id, reason="expired")
        return {
            "ok": False,
            "status": "expired",
            "spoken": "Señor, ese borrador expiró. ¿Quiere que lo prepare de nuevo?",
            "transition": "transition_to_general_assistant",
        }

    status = str(draft.get("status") or "")
    if status == "sent":
        mid = draft.get("sent_message_id") or ""
        suffix = f" (ref. {mid[:8]})" if mid else ""
        return {
            "ok": True,
            "status": "already_sent",
            "spoken": f"Señor, ese correo ya fue enviado{suffix}.",
            "transition": "transition_to_general_assistant",
        }
    if status == "cancelled":
        return {
            "ok": False,
            "status": "cancelled",
            "spoken": "Señor, ese envío fue cancelado. ¿Desea preparar otro correo?",
            "transition": "transition_to_general_assistant",
        }
    if status == "sending":
        return {
            "ok": True,
            "status": "in_progress",
            "spoken": "Señor, el envío ya está en curso. Un momento, por favor.",
        }

    user_line = _latest_user_utterance(payload)
    transcript = _transcript_from_payload(payload)
    if not is_gmail_send_confirm(user_line, allow_short_yes=True):
        return {
            "ok": False,
            "status": "confirm_required",
            "spoken": (
                "Señor, no detecté una confirmación clara. "
                "¿Desea que envíe el correo? Diga «sí, envíalo» o «cancela»."
            ),
        }
    if not _agent_recently_asked_confirm(transcript):
        return {
            "ok": False,
            "status": "confirm_context_missing",
            "spoken": (
                "Señor, confirme explícitamente el envío: "
                "«sí, envíalo» o «no, cancela»."
            ),
        }

    if not vcs.try_mark_gmail_pending_sending(user_id, str(draft.get("draft_id") or "")):
        refreshed = vcs.get_gmail_pending_send(user_id) or {}
        if refreshed.get("status") == "sent":
            return {
                "ok": True,
                "status": "already_sent",
                "spoken": "Señor, ese correo ya fue enviado.",
                "transition": "transition_to_general_assistant",
            }
        return {
            "ok": False,
            "status": "race",
            "spoken": "Señor, hubo un conflicto con el borrador. Intente de nuevo.",
        }

    to_addr = str(draft.get("to") or "")
    subject = str(draft.get("subject") or "")
    body = str(draft.get("body") or "")

    try:
        def _send(access: str) -> dict[str, Any]:
            return send_message(access, to=to_addr, subject=subject, body=body)

        result = _gmail_api_call(user_id, _send)
        message_id = str(result.get("id") or "")
        vcs.mark_gmail_pending_sent(user_id, message_id=message_id)
        logger.info(
            "[GMAIL-SEND] sent user=%s draft=%s to=%s",
            user_id[:8],
            str(draft.get("draft_id", ""))[:8],
            to_addr,
        )
        return {
            "ok": True,
            "status": "sent",
            "message_id": message_id,
            "spoken": f"Señor, envié el correo a {to_addr}.",
            "transition": "transition_to_general_assistant",
        }
    except ValueError as exc:
        vcs.revert_gmail_pending_to_pending(user_id)
        if str(exc) == "not_connected":
            return {"ok": False, "status": "not_connected", "spoken": _not_connected_message()}
        return {
            "ok": False,
            "status": "error",
            "spoken": "Señor, no pude enviar el correo. Verifique Gmail conectado.",
        }
    except httpx.HTTPStatusError as exc:
        vcs.revert_gmail_pending_to_pending(user_id)
        logger.warning("[GMAIL-SEND] HTTP %s user=%s", exc.response.status_code, user_id[:8])
        if exc.response.status_code in (401, 403):
            return {"ok": False, "status": "auth", "spoken": _reconnect_message()}
        return {
            "ok": False,
            "status": "error",
            "spoken": "Señor, Gmail rechazó el envío. ¿Lo intento de nuevo?",
        }
    except Exception:  # noqa: BLE001
        vcs.revert_gmail_pending_to_pending(user_id)
        logger.exception("[GMAIL-SEND] failed user=%s", user_id[:8])
        return {
            "ok": False,
            "status": "error",
            "spoken": "Señor, no pude enviar el correo en este momento.",
        }


def cancel_gmail_send(
    user_id: str,
    *,
    draft_id: str = "",
    reason: str = "user_cancel",
) -> dict[str, Any]:
    draft = vcs.get_gmail_pending_send(user_id)
    if not draft:
        return {
            "ok": True,
            "status": "no_draft",
            "spoken": "No hay correo pendiente, señor.",
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
    if draft.get("status") == "sent":
        return {
            "ok": True,
            "status": "already_sent",
            "spoken": "Señor, ese correo ya fue enviado; no puedo cancelarlo.",
            "transition": "transition_to_general_assistant",
        }
    vcs.clear_gmail_pending_send(user_id, reason=reason)
    return {
        "ok": True,
        "status": "cancelled",
        "spoken": "Entendido, señor. No enviaré ese correo.",
        "transition": "transition_to_general_assistant",
    }


def maybe_clear_gmail_pending_on_topic_change(user_id: str, tool_name: str) -> None:
    """Auto-cancela borrador si el usuario cambia de tema (otra tool)."""
    if tool_name in {
        "gmail_prepare_send",
        "gmail_confirm_send",
        "gmail_cancel_send",
    }:
        return
    if vcs.get_gmail_pending_send(user_id):
        vcs.clear_gmail_pending_send(user_id, reason="topic_change")
        logger.info("[GMAIL-SEND] cleared pending user=%s tool=%s", user_id[:8], tool_name)


def clear_gmail_pending_for_call(user_id: str, call_id: str) -> None:
    draft = vcs.get_gmail_pending_send(user_id)
    if not draft:
        return
    bound = str(draft.get("call_id") or "").strip()
    if bound and call_id and bound != call_id.strip():
        return
    vcs.clear_gmail_pending_send(user_id, reason="call_ended")
