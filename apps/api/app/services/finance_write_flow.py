"""Flujo Finanzas escritura con confirmación — piloto Retell nativo (staging)."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any, Literal

from app.modules.finance_module import (
    _confirm_pending_spoken,
    _confirm_spoken,
    is_finance_future_write,
    is_finance_pending_write,
    is_finance_write_intent,
    parse_finance_statement,
    parse_pending_statements,
)
from app.services import voice_client_session as vcs
from app.services.finance_ledger import save_transaction

logger = logging.getLogger(__name__)

FINANCE_WRITE_TTL_SEC = 600
DraftStatus = Literal["pending", "writing", "written", "cancelled"]

_FINANCE_WRITE_CONFIRM = re.compile(
    r"\b("
    r"s[ií]\s*,?\s*(?:reg[ií]stra(?:lo|la|me|r)?|anota(?:lo|la|me|r)?|confirma(?:lo)?|gu[aá]rdalo)|"
    r"reg[ií]stra(?:lo|la|me|r)?|anota(?:lo|la|me|r)?|gu[aá]rdalo|"
    r"dale|adelante|de\s+acuerdo|confirmo|confirma(?:do)?|correcto|exacto|"
    r"procede|hazlo|s[ií]\s+por\s+favor"
    r")\b",
    re.I,
)

_FINANCE_WRITE_CANCEL = re.compile(
    r"\b("
    r"no\s*,?\s*(?:registres|anotes|lo\s+hagas|gu[aá]rdes)?|"
    r"cancela(?:r)?|olv[ií]dalo|olvidalo|mejor\s+no|"
    r"no\s+lo\s+registres|detente|para"
    r")\b",
    re.I,
)

_AGENT_CONFIRM_ASK = re.compile(
    r"\b(confirm(?:o|a|ar|e)?|registr(?:o|e|ar)|anot(?:o|e|ar)|guard(?:o|e|ar)|preparad|"
    r"¿\s*desea|desea\s+que|procedo|pendiente)\b",
    re.I,
)

_SHORT_AFFIRMATIVE = re.compile(
    r"^(?:s[ií]|dale|adelante|correcto|exacto|confirmo|de\s+acuerdo|ok(?:ay)?)[\s!.]*$",
    re.I,
)


def is_finance_write_confirm(text: str, *, allow_short_yes: bool = False) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if allow_short_yes and _SHORT_AFFIRMATIVE.match(t):
        return True
    if re.fullmatch(r"s[ií]\s*(?:reg[ií]stra(?:lo|la)?|anota(?:lo|la)?)[\s!.]*", t, re.I):
        return True
    return bool(_FINANCE_WRITE_CONFIRM.search(t))


def is_short_finance_affirmative(text: str) -> bool:
    return bool(_SHORT_AFFIRMATIVE.match((text or "").strip()))


def is_finance_write_cancel(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_FINANCE_WRITE_CANCEL.search(t))


def _idempotency_key(user_id: str, draft_id: str) -> str:
    raw = f"{user_id}:{draft_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


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


def _summarize_draft_rows(kind: str, rows: list[dict[str, Any]]) -> str:
    from app.services.finance_speech import amount_to_spoken_es, due_date_to_spoken_es

    if kind == "pending":
        parts: list[str] = []
        for row in rows:
            money = amount_to_spoken_es(row.get("amount"), "USD")
            cat = str(row.get("category") or "").strip()
            due_time = str(row.get("due_time") or "").strip() or None
            when = due_date_to_spoken_es(row.get("due_date"), due_time=due_time)
            segment = f"pago pendiente de {money}"
            if cat:
                segment += f" de {cat}"
            if row.get("due_date") or due_time:
                segment += f" para {when}"
            parts.append(segment)
        if len(parts) == 1:
            return f"Señor, {parts[0]}. ¿Desea que lo registre?"
        return (
            f"Señor, registraré {len(parts)} pagos pendientes: "
            f"{'; '.join(parts)}. ¿Desea confirmar?"
        )

    row = rows[0]
    tx_type = str(row.get("type") or "gasto")
    kind_label = "ingreso" if tx_type == "ingreso" else "gasto"
    money = amount_to_spoken_es(row.get("amount"), "USD")
    cat = row.get("category")
    cat_txt = f" en {cat}" if cat else ""
    return (
        f"Señor, un {kind_label} de {money}{cat_txt}. "
        f"¿Desea que lo registre?"
    )


def prepare_finance_write(
    user_id: str,
    *,
    call_id: str,
    query: str = "",
) -> dict[str, Any]:
    """Valida y crea borrador pending — nunca guarda en BD."""
    text = (query or "").strip()
    if not text:
        return {
            "ok": False,
            "status": "needs_query",
            "spoken": "Señor, ¿qué movimiento desea registrar? Indique monto y concepto.",
        }

    kind = ""
    rows: list[dict[str, Any]] = []

    if is_finance_pending_write(text):
        parsed_rows = parse_pending_statements(text)
        if not parsed_rows:
            return {
                "ok": False,
                "status": "needs_details",
                "spoken": (
                    "Señor, no entendí el pago pendiente. "
                    "¿Me lo repite con monto y día?"
                ),
            }
        kind = "pending"
        rows = parsed_rows
    elif is_finance_write_intent(text):
        parsed = parse_finance_statement(text)
        if not parsed:
            return {
                "ok": False,
                "status": "needs_details",
                "spoken": (
                    "Señor, no entendí el movimiento. "
                    "¿Es un gasto o ingreso, con qué monto?"
                ),
            }
        kind = "transaction"
        rows = [parsed]
    elif is_finance_future_write(text):
        parsed_rows = parse_pending_statements(text)
        if not parsed_rows:
            return {
                "ok": False,
                "status": "needs_details",
                "spoken": (
                    "Señor, no entendí el pago pendiente. "
                    "¿Me lo repite con monto y día?"
                ),
            }
        kind = "pending"
        rows = parsed_rows
    else:
        return {
            "ok": False,
            "status": "not_a_write",
            "spoken": (
                "Señor, para registrar finanzas necesito un monto y concepto, "
                "por ejemplo «gasté 50 en materiales»."
            ),
        }

    draft_id = str(uuid.uuid4())
    draft = {
        "draft_id": draft_id,
        "call_id": (call_id or "").strip(),
        "kind": kind,
        "rows": rows,
        "status": "pending",
        "idempotency_key": _idempotency_key(user_id, draft_id),
        "saved_ids": [],
    }
    vcs.set_finance_pending_write(user_id, draft)
    spoken = _summarize_draft_rows(kind, rows)
    return {
        "ok": True,
        "status": "awaiting_confirmation",
        "draft_id": draft_id,
        "kind": kind,
        "spoken": (
            f"{spoken} "
        "Cuando el usuario confirme con «sí» o «dale», llame finance_confirm_write."
        ),
        "transition": "transition_to_finance_confirm_pending",
    }


def _execute_draft_rows(user_id: str, draft: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    from app.services.finance_speech import embed_due_time_in_description

    kind = str(draft.get("kind") or "")
    rows = draft.get("rows") or []
    if not isinstance(rows, list):
        return [], "Sin filas en el borrador."

    saved_list: list[dict[str, Any]] = []
    last_error = ""

    if kind == "pending":
        for row in rows:
            if not isinstance(row, dict):
                continue
            due_time = str(row.get("due_time") or "").strip() or None
            description = embed_due_time_in_description(
                str(row.get("description") or "") or None,
                due_time,
            )
            saved = save_transaction(
                user_id,
                tx_type="gasto",
                amount=row.get("amount"),
                category=row.get("category"),  # type: ignore[arg-type]
                description=description,
                status="pendiente",
                due_date=row.get("due_date"),
            )
            if saved.get("ok"):
                saved.setdefault("category", row.get("category"))
                if due_time:
                    saved["due_time"] = due_time
                saved_list.append(saved)
            else:
                last_error = str(saved.get("error") or last_error)
    else:
        row = rows[0] if rows else {}
        if isinstance(row, dict):
            saved = save_transaction(
                user_id,
                tx_type=str(row.get("type") or "gasto"),
                amount=row.get("amount"),
                category=row.get("category"),  # type: ignore[arg-type]
                description=row.get("description"),  # type: ignore[arg-type]
                occurred_on=row.get("occurred_on"),
            )
            if saved.get("ok"):
                saved_list.append(saved)
            else:
                last_error = str(saved.get("error") or "")

    if saved_list:
        if kind == "pending":
            return saved_list, _confirm_pending_spoken(saved_list)
        return saved_list, _confirm_spoken(saved_list[0])

    schema_hint = f" Detalle: {last_error[:120]}." if last_error else ""
    return [], (
        "Señor, no pude guardar el movimiento."
        f"{schema_hint} Revise que la base de datos de finanzas esté lista."
    )


def confirm_finance_write(
    user_id: str,
    *,
    call_id: str,
    payload: dict[str, Any],
    draft_id: str = "",
) -> dict[str, Any]:
    """Guarda solo con confirmación explícita verificada en el transcript."""
    draft = vcs.get_finance_pending_write(user_id)
    if not draft:
        return {
            "ok": False,
            "status": "no_draft",
            "spoken": "Señor, no tengo un movimiento pendiente de registrar.",
            "transition": "transition_to_general_assistant",
        }

    wanted = (draft_id or "").strip()
    if wanted and wanted != draft.get("draft_id"):
        return {
            "ok": False,
            "status": "draft_mismatch",
            "spoken": "Señor, ese borrador ya no está activo. ¿Desea prepararlo de nuevo?",
            "transition": "transition_to_general_assistant",
        }

    if vcs.is_finance_pending_write_expired(user_id):
        vcs.clear_finance_pending_write(user_id, reason="expired")
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
            "spoken": "Señor, ese movimiento ya fue registrado.",
            "transition": "transition_to_general_assistant",
        }
    if status == "cancelled":
        return {
            "ok": False,
            "status": "cancelled",
            "spoken": "Señor, ese registro fue cancelado. ¿Desea preparar otro?",
            "transition": "transition_to_general_assistant",
        }
    if status == "writing":
        return {
            "ok": True,
            "status": "in_progress",
            "spoken": "Señor, el registro ya está en curso. Un momento, por favor.",
        }

    user_line = _latest_user_utterance(payload)
    transcript = _transcript_from_payload(payload)
    logger.info(
        "[FINANCE-WRITE] confirm attempt user=%s draft=%s utterance=%r",
        user_id[:8],
        str(draft.get("draft_id", ""))[:8],
        user_line[:80],
    )
    if not is_finance_write_confirm(user_line, allow_short_yes=True):
        return {
            "ok": False,
            "status": "confirm_required",
            "spoken": (
                "Señor, no detecté una confirmación clara. "
                "¿Desea que lo registre? Diga «sí» o «cancela»."
            ),
        }
    short_yes = is_short_finance_affirmative(user_line)
    if not short_yes and not _agent_recently_asked_confirm(transcript):
        return {
            "ok": False,
            "status": "confirm_context_missing",
            "spoken": (
                "Señor, confirme explícitamente el registro: "
                "«sí» o «no, cancela»."
            ),
        }

    if not vcs.try_mark_finance_pending_writing(user_id, str(draft.get("draft_id") or "")):
        refreshed = vcs.get_finance_pending_write(user_id) or {}
        if refreshed.get("status") == "written":
            return {
                "ok": True,
                "status": "already_written",
                "spoken": "Señor, ese movimiento ya fue registrado.",
                "transition": "transition_to_general_assistant",
            }
        return {
            "ok": False,
            "status": "race",
            "spoken": "Señor, hubo un conflicto con el borrador. Intente de nuevo.",
        }

    try:
        saved_list, spoken = _execute_draft_rows(user_id, draft)
        if not saved_list:
            vcs.revert_finance_pending_to_pending(user_id)
            return {"ok": False, "status": "error", "spoken": spoken}

        saved_ids = [str(s.get("id") or "") for s in saved_list if s.get("id")]
        vcs.mark_finance_pending_written(user_id, saved_ids=saved_ids)
        logger.info(
            "[FINANCE-WRITE] saved user=%s draft=%s count=%s",
            user_id[:8],
            str(draft.get("draft_id", ""))[:8],
            len(saved_list),
        )
        return {
            "ok": True,
            "status": "written",
            "saved_ids": saved_ids,
            "spoken": spoken,
            "transition": "transition_to_general_assistant",
        }
    except Exception:  # noqa: BLE001
        vcs.revert_finance_pending_to_pending(user_id)
        logger.exception("[FINANCE-WRITE] failed user=%s", user_id[:8])
        return {
            "ok": False,
            "status": "error",
            "spoken": "Señor, no pude registrar el movimiento en este momento.",
        }


def cancel_finance_write(
    user_id: str,
    *,
    draft_id: str = "",
    reason: str = "user_cancel",
) -> dict[str, Any]:
    draft = vcs.get_finance_pending_write(user_id)
    if not draft:
        return {
            "ok": True,
            "status": "no_draft",
            "spoken": "No hay movimiento pendiente, señor.",
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
            "spoken": "Señor, ese movimiento ya fue registrado; no puedo cancelarlo.",
            "transition": "transition_to_general_assistant",
        }
    vcs.clear_finance_pending_write(user_id, reason=reason)
    return {
        "ok": True,
        "status": "cancelled",
        "spoken": "Entendido, señor. No registraré ese movimiento.",
        "transition": "transition_to_general_assistant",
    }


def maybe_clear_finance_pending_on_topic_change(user_id: str, tool_name: str) -> None:
    """Auto-cancela borrador si el usuario cambia de tema (otra tool)."""
    if tool_name in {
        "finance_prepare_write",
        "finance_confirm_write",
        "finance_cancel_write",
    }:
        return
    if vcs.get_finance_pending_write(user_id):
        vcs.clear_finance_pending_write(user_id, reason="topic_change")
        logger.info("[FINANCE-WRITE] cleared pending user=%s tool=%s", user_id[:8], tool_name)


def clear_finance_pending_for_call(user_id: str, call_id: str) -> None:
    draft = vcs.get_finance_pending_write(user_id)
    if not draft:
        return
    bound = str(draft.get("call_id") or "").strip()
    if bound and call_id and bound != call_id.strip():
        return
    vcs.clear_finance_pending_write(user_id, reason="call_ended")
