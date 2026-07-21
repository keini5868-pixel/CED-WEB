"""Flujo Calendario escritura con confirmación — piloto Retell nativo."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx

from app.modules.calendar_module import (
    _calendar_api_call,
    _extract_title,
    _not_connected_message,
    _parse_target_day,
    _parse_time,
)
from app.services import voice_client_session as vcs
from app.services.google_calendar_api import create_event
from app.services.google_oauth import get_valid_access_token, token_has_calendar_write_scope

logger = logging.getLogger(__name__)

CALENDAR_WRITE_TTL_SEC = 600
DraftStatus = Literal["pending", "writing", "written", "cancelled"]

# Palabra "sí/si" aislada — el confirmador real y más frecuente en voz. Se usa con
# \b para no matchear dentro de otras palabras ("así", "revisión").
_YES_WORD = re.compile(r"\bs[ií]\b", re.I)

_CALENDAR_WRITE_CONFIRM = re.compile(
    r"\b("
    r"ag[eé]nda(?:lo|la|me|r)?|gu[aá]rdalo|"
    r"dale|adelante|de\s+acuerdo|confirmo|conf[ií]rma(?:do|lo)?|correcto|exacto|"
    r"procede|hazlo|claro|as[ií]\s+es|est[aá]\s+bien|obvio|"
    r"perfecto|de\s+una|hag[aá]moslo"
    r")\b",
    re.I,
)

_CALENDAR_WRITE_CANCEL = re.compile(
    r"\b("
    r"no\s+lo\s+agendes|no\s+lo\s+hagas|no\s+lo\s+guardes|"
    r"cancela(?:r|lo)?|olv[ií]dalo|olvidalo|mejor\s+no|"
    r"detente|espera|todav[ií]a\s+no|a[uú]n\s+no"
    r")\b",
    re.I,
)

_AGENT_CONFIRM_ASK = re.compile(
    r"\b(confirm(?:o|a|ar|e)?|agenda(?:r|lo)?|guard(?:o|e|ar)|prepar[ée]|preparad|"
    r"¿\s*desea|desea\s+que|procedo|pendiente|registro|anoto)\b",
    re.I,
)

# Ruido de cortesía / muletillas frecuentes en voz que no cambian el significado
# de la respuesta ("Sí señor", "Sí, por favor", "Eh, sí", "Sí, gracias"...).
# Se elimina antes de contar palabras para decidir si es una afirmación corta.
_CONFIRM_NOISE = re.compile(
    r"\b(por\s+favor|se[nñ]or(?:a)?|gracias|eh+|ehh+|bueno|vale|okay|ok)\b",
    re.I,
)

# Amplio a propósito: esta regex solo corre DESPUÉS de que el LLM ya decidió
# invocar calendar_prepare_write, así que el riesgo de falso positivo es bajo
# y el costo de un falso negativo (pedir aclaración de la nada) es alto — el
# usuario dice "guarda", "anota", "apunta", "pon", "reserva", "registra" con
# la misma frecuencia que "agéndame" para pedir agendar algo.
_WRITE_INTENT = re.compile(
    r"\b(?:"
    r"ag[eé]nda(?:me)?|agendar|programa(?:r|me)?|recu[eé]rdame|"
    r"guarda(?:me)?|an[oó]ta(?:me)?|apunta(?:me)?|reserva(?:me)?|"
    r"registra(?:me)?|ponme"
    r")\b",
    re.I,
)


def is_calendar_write_intent(text: str) -> bool:
    return bool(_WRITE_INTENT.search(text or ""))


def _strip_confirm_noise(text: str) -> str:
    cleaned = _CONFIRM_NOISE.sub(" ", text or "")
    cleaned = re.sub(r"[^\w\sáéíóúñÁÉÍÓÚÑ]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def is_calendar_write_confirm(text: str, *, allow_short_yes: bool = False) -> bool:
    """True si el usuario confirma agendar. Tolerante a ruido real de voz:
    puntuación STT ("Sí,"), vocativos ("Sí señor"), cortesía ("Sí, por favor")
    y muletillas ("Eh, sí"). No usar `allow_short_yes` no cambia el resultado —
    se mantiene el parámetro por compatibilidad con las llamadas existentes.
    """
    t = (text or "").strip()
    if not t:
        return False
    if _YES_WORD.search(t):
        return True
    return bool(_CALENDAR_WRITE_CONFIRM.search(t))


def is_short_calendar_affirmative(text: str) -> bool:
    """True si, tras quitar cortesía/muletillas, queda una afirmación corta
    (<=5 palabras) — permite saltar la verificación de contexto del agente
    cuando la respuesta del usuario es un "sí" inequívoco aunque venga con
    ruido natural de voz alrededor.
    """
    t = (text or "").strip()
    if not t:
        return False
    cleaned = _strip_confirm_noise(t)
    if not cleaned:
        return False
    if len(cleaned.split()) > 5:
        return False
    return bool(_YES_WORD.search(cleaned) or _CALENDAR_WRITE_CONFIRM.search(cleaned))


def is_calendar_write_cancel(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_CALENDAR_WRITE_CANCEL.search(t))


def _idempotency_key(user_id: str, draft_id: str) -> str:
    return hashlib.sha256(f"{user_id}:{draft_id}".encode()).hexdigest()


def _transcript_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    call = payload.get("call") or {}
    obj = call.get("transcript_object") or call.get("transcriptObject") or []
    return obj if isinstance(obj, list) else []


def _latest_user_utterance(payload: dict[str, Any]) -> str:
    """Última frase del usuario en el payload Retell.

    Misma lógica que Finance/Gmail: primero `transcript_object`, y si viene
    vacío/atrasado (caso frecuente al invocar confirm en el mismo turno),
    cae a `call.transcript` en texto. Sin este fallback, confirm falla con
    utterance='' → bucle de «¿Desea que lo agende?» sin llamar a Google.
    """
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


def _agent_recently_asked_confirm(transcript: list[dict[str, Any]]) -> bool:
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


def _missing_write_scope_message() -> str:
    return (
        "Señor, falta permiso de escritura en Google Calendar. "
        "Reconecte Calendar en configuración de voz concediendo acceso completo "
        "(no solo lectura) e intente de nuevo."
    )


def _parse_event_draft(query: str) -> dict[str, Any] | None:
    text = (query or "").strip()
    if not text or not is_calendar_write_intent(text):
        return None
    reminder = bool(re.search(r"recu[eé]rdame", text, re.I))
    try:
        tz: ZoneInfo | Any = ZoneInfo("America/New_York")
    except Exception:  # noqa: BLE001
        from datetime import timezone as dt_tz

        tz = dt_tz.utc
    day = _parse_target_day(text, tz)  # type: ignore[arg-type]
    hour, minute = _parse_time(text)
    start = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    title = _extract_title(text, reminder=reminder)
    if reminder and not title.lower().startswith("recordatorio"):
        title = f"Recordatorio: {title}"
    return {
        "title": title,
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
        "tz_name": "America/New_York",
        "reminder": reminder,
        "when_spoken": start.strftime("%A %d/%m a las %I:%M %p").replace(" 0", " "),
    }


def prepare_calendar_write(
    user_id: str,
    *,
    call_id: str,
    query: str = "",
) -> dict[str, Any]:
    """Crea borrador de evento — nunca escribe en Google Calendar."""
    parsed = _parse_event_draft(query)
    if not parsed:
        return {
            "ok": False,
            "status": "needs_details",
            "spoken": (
                "Señor, indíqueme qué desea agendar: por ejemplo "
                "«agéndame reunión con Ana mañana a las 3 pm»."
            ),
        }

    # Verificación temprana de conexión y permiso de escritura.
    try:
        access = get_valid_access_token("calendar", user_id)
        if not token_has_calendar_write_scope(access):
            return {
                "ok": False,
                "status": "missing_write_scope",
                "spoken": _missing_write_scope_message(),
            }
    except ValueError as exc:
        if str(exc) == "not_connected":
            return {
                "ok": False,
                "status": "not_connected",
                "spoken": _not_connected_message(),
            }
        return {
            "ok": False,
            "status": "error",
            "spoken": "Señor, no pude acceder a su calendario. Revise la conexión.",
        }

    draft_id = str(uuid.uuid4())
    kind = "recordatorio" if parsed["reminder"] else "cita"
    draft = {
        "draft_id": draft_id,
        "call_id": (call_id or "").strip(),
        "kind": kind,
        "title": parsed["title"],
        "start_iso": parsed["start_iso"],
        "end_iso": parsed["end_iso"],
        "tz_name": parsed["tz_name"],
        "reminder": parsed["reminder"],
        "when_spoken": parsed["when_spoken"],
        "status": "pending",
        "idempotency_key": _idempotency_key(user_id, draft_id),
        "created_event_id": None,
    }
    vcs.set_calendar_pending_write(user_id, draft)
    # Misma pista al LLM que Finance: sin ella Retell puede re-preguntar en voz
    # sin invocar calendar_confirm_write, y el evento nunca se crea.
    spoken = (
        f"Señor, preparé su {kind} «{parsed['title']}» para {parsed['when_spoken']}. "
        f"¿Desea que lo agende en su calendario? "
        "Cuando el usuario confirme con «sí» o «dale», llame calendar_confirm_write."
    )
    return {
        "ok": True,
        "status": "awaiting_confirmation",
        "draft_id": draft_id,
        "spoken": spoken,
        "transition": "transition_to_calendar_confirm_pending",
    }


def confirm_calendar_write(
    user_id: str,
    *,
    call_id: str,
    payload: dict[str, Any],
    draft_id: str = "",
) -> dict[str, Any]:
    """Escribe el evento solo con confirmación explícita en el transcript."""
    draft = vcs.get_calendar_pending_write(user_id)
    if not draft:
        logger.warning(
            "[CALENDAR-WRITE] confirm FAILED status=no_draft user=%s draft_id_arg=%r "
            "(no hay borrador en memoria para este user_id — revisar si prepare_write "
            "se ejecutó con el mismo user_id resuelto, o si expiró/fue limpiado antes)",
            user_id[:8],
            draft_id,
        )
        return {
            "ok": False,
            "status": "no_draft",
            "spoken": "Señor, no tengo una cita pendiente de agendar.",
            "transition": "transition_to_general_assistant",
        }

    wanted = (draft_id or "").strip()
    if wanted and wanted != draft.get("draft_id"):
        logger.warning(
            "[CALENDAR-WRITE] confirm FAILED status=draft_mismatch user=%s wanted=%r actual=%r",
            user_id[:8],
            wanted,
            draft.get("draft_id"),
        )
        return {
            "ok": False,
            "status": "draft_mismatch",
            "spoken": "Señor, ese borrador ya no está activo. ¿Desea preparar la cita de nuevo?",
            "transition": "transition_to_general_assistant",
        }

    if vcs.is_calendar_pending_write_expired(user_id):
        vcs.clear_calendar_pending_write(user_id, reason="expired")
        logger.warning(
            "[CALENDAR-WRITE] confirm FAILED status=expired user=%s draft=%s",
            user_id[:8],
            str(draft.get("draft_id", ""))[:8],
        )
        return {
            "ok": False,
            "status": "expired",
            "spoken": "Señor, ese borrador expiró. ¿Quiere que lo prepare de nuevo?",
            "transition": "transition_to_general_assistant",
        }

    status = str(draft.get("status") or "")
    if status == "written":
        return {
            "ok": True,
            "status": "already_written",
            "spoken": "Señor, esa cita ya fue agendada.",
            "transition": "transition_to_general_assistant",
        }
    if status == "cancelled":
        return {
            "ok": False,
            "status": "cancelled",
            "spoken": "Señor, esa agenda fue cancelada. ¿Desea preparar otra?",
            "transition": "transition_to_general_assistant",
        }
    if status == "writing":
        return {
            "ok": True,
            "status": "in_progress",
            "spoken": "Señor, el registro de la cita ya está en curso. Un momento.",
        }

    user_line = _latest_user_utterance(payload)
    transcript = _transcript_from_payload(payload)
    logger.info(
        "[CALENDAR-WRITE] confirm attempt user=%s draft=%s utterance=%r "
        "transcript_obj_len=%d has_transcript_str=%s",
        user_id[:8],
        str(draft.get("draft_id", ""))[:8],
        user_line[:80],
        len(transcript),
        bool(str((payload.get("call") or {}).get("transcript") or "").strip()),
    )
    if not user_line:
        # Carrera Retell: el modelo ya llamó calendar_confirm_write (solo debe
        # hacerlo tras un «sí») pero el payload aún no trae la frase. Con
        # borrador pending, aceptar la invocación del tool como confirmación.
        logger.warning(
            "[CALENDAR-WRITE] empty utterance with pending draft user=%s — "
            "treating calendar_confirm_write invoke as affirmative (Retell race)",
            user_id[:8],
        )
        user_line = "sí"
    if not is_calendar_write_confirm(user_line, allow_short_yes=True):
        logger.warning(
            "[CALENDAR-WRITE] confirm FAILED status=confirm_required user=%s utterance=%r "
            "(is_calendar_write_confirm devolvió False para esta frase)",
            user_id[:8],
            user_line[:120],
        )
        return {
            "ok": False,
            "status": "confirm_required",
            "spoken": (
                "Señor, no detecté una confirmación clara. "
                "¿Desea que lo agende? Diga «sí» o «cancela»."
            ),
        }
    short_yes = is_short_calendar_affirmative(user_line)
    if not short_yes and not _agent_recently_asked_confirm(transcript):
        logger.warning(
            "[CALENDAR-WRITE] confirm FAILED status=confirm_context_missing user=%s utterance=%r "
            "agent_lines_checked=%d (ninguna línea reciente del agente coincidió con "
            "_AGENT_CONFIRM_ASK y la frase no calificó como short_yes)",
            user_id[:8],
            user_line[:120],
            len(transcript),
        )
        return {
            "ok": False,
            "status": "confirm_context_missing",
            "spoken": (
                "Señor, confirme explícitamente: «sí» o «no, cancela»."
            ),
        }

    if not vcs.try_mark_calendar_pending_writing(user_id, str(draft.get("draft_id") or "")):
        refreshed = vcs.get_calendar_pending_write(user_id) or {}
        if refreshed.get("status") == "written":
            return {
                "ok": True,
                "status": "already_written",
                "spoken": "Señor, esa cita ya fue agendada.",
                "transition": "transition_to_general_assistant",
            }
        logger.warning(
            "[CALENDAR-WRITE] confirm FAILED status=race user=%s draft=%s refreshed_status=%r",
            user_id[:8],
            str(draft.get("draft_id", ""))[:8],
            refreshed.get("status"),
        )
        return {
            "ok": False,
            "status": "race",
            "spoken": "Señor, hubo un conflicto con el borrador. Intente de nuevo.",
        }

    title = str(draft.get("title") or "Cita CED")
    kind = str(draft.get("kind") or "cita")
    when = str(draft.get("when_spoken") or "")
    try:
        start = datetime.fromisoformat(str(draft["start_iso"]))
        end = datetime.fromisoformat(str(draft["end_iso"]))
    except Exception:  # noqa: BLE001
        vcs.revert_calendar_pending_to_pending(user_id)
        return {
            "ok": False,
            "status": "error",
            "spoken": "Señor, el borrador de fecha es inválido. Prepare la cita de nuevo.",
        }

    try:
        access = get_valid_access_token("calendar", user_id)
        if not token_has_calendar_write_scope(access):
            vcs.revert_calendar_pending_to_pending(user_id)
            return {
                "ok": False,
                "status": "missing_write_scope",
                "spoken": _missing_write_scope_message(),
                "transition": "transition_to_general_assistant",
            }

        def _create(tok: str) -> dict[str, Any]:
            return create_event(
                tok,
                summary=title,
                start=start,
                end=end,
                tz_name=str(draft.get("tz_name") or "America/New_York"),
            )

        created = _calendar_api_call(user_id, _create)
        event_id = str((created or {}).get("id") or "")
        vcs.mark_calendar_pending_written(user_id, event_id=event_id)
        logger.info(
            "[CALENDAR-WRITE] saved user=%s draft=%s event=%s",
            user_id[:8],
            str(draft.get("draft_id", ""))[:8],
            event_id[:12],
        )
        return {
            "ok": True,
            "status": "written",
            "event_id": event_id,
            "spoken": f"Señor, agendé su {kind} «{title}» para {when}.",
            "transition": "transition_to_general_assistant",
        }
    except ValueError as exc:
        vcs.revert_calendar_pending_to_pending(user_id)
        if str(exc) == "not_connected":
            return {
                "ok": False,
                "status": "not_connected",
                "spoken": _not_connected_message(),
                "transition": "transition_to_general_assistant",
            }
        logger.warning(
            "[CALENDAR-WRITE] confirm FAILED status=error(ValueError) user=%s reason=%r",
            user_id[:8],
            str(exc)[:200],
        )
        return {
            "ok": False,
            "status": "error",
            "spoken": (
                "Señor, falló el agendado (error de validación). "
                "No quedó registrado en Google Calendar. ¿Lo intento de nuevo?"
            ),
        }
    except httpx.HTTPStatusError as exc:
        vcs.revert_calendar_pending_to_pending(user_id)
        code = exc.response.status_code
        logger.warning("[CALENDAR-WRITE] HTTP %s user=%s", code, user_id[:8])
        body = (exc.response.text or "")[:300].lower()
        if code in (401, 403) and (
            "insufficient" in body
            or "permission" in body
            or "scope" in body
            or "accessnotconfigured" in body
        ):
            return {
                "ok": False,
                "status": "missing_write_scope",
                "spoken": _missing_write_scope_message(),
                "transition": "transition_to_general_assistant",
            }
        if code in (401, 403):
            return {
                "ok": False,
                "status": "auth",
                "spoken": _missing_write_scope_message(),
                "transition": "transition_to_general_assistant",
            }
        return {
            "ok": False,
            "status": "error",
            "spoken": (
                f"Señor, Google Calendar rechazó el evento (código {code}). "
                "No quedó agendado. ¿Lo intento de nuevo?"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        vcs.revert_calendar_pending_to_pending(user_id)
        logger.exception("[CALENDAR-WRITE] failed user=%s", user_id[:8])
        detail = str(exc).strip()[:80]
        return {
            "ok": False,
            "status": "error",
            "spoken": (
                "Señor, no pude agendar en su calendario: "
                f"{detail or 'error interno'}. No quedó registrado. "
                "¿Lo intento de nuevo?"
            ),
        }


def cancel_calendar_write(
    user_id: str,
    *,
    draft_id: str = "",
    reason: str = "user_cancel",
) -> dict[str, Any]:
    draft = vcs.get_calendar_pending_write(user_id)
    if not draft:
        return {
            "ok": True,
            "status": "no_draft",
            "spoken": "No hay cita pendiente, señor.",
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
    if draft.get("status") == "written":
        return {
            "ok": True,
            "status": "already_written",
            "spoken": "Señor, esa cita ya fue agendada; no puedo cancelarla desde aquí.",
            "transition": "transition_to_general_assistant",
        }
    vcs.clear_calendar_pending_write(user_id, reason=reason)
    return {
        "ok": True,
        "status": "cancelled",
        "spoken": "Entendido, señor. No agendaré esa cita.",
        "transition": "transition_to_general_assistant",
    }


def maybe_clear_calendar_pending_on_topic_change(user_id: str, tool_name: str) -> None:
    if tool_name in {
        "calendar_prepare_write",
        "calendar_confirm_write",
        "calendar_cancel_write",
    }:
        return
    if vcs.get_calendar_pending_write(user_id):
        vcs.clear_calendar_pending_write(user_id, reason="topic_change")
        logger.info(
            "[CALENDAR-WRITE] cleared pending user=%s tool=%s",
            user_id[:8],
            tool_name,
        )


def clear_calendar_pending_for_call(user_id: str, call_id: str) -> None:
    draft = vcs.get_calendar_pending_write(user_id)
    if not draft:
        return
    bound = str(draft.get("call_id") or "").strip()
    if bound and call_id and bound != call_id.strip():
        return
    vcs.clear_calendar_pending_write(user_id, reason="call_ended")
