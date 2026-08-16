"""Finanzas personales — persistencia y agregación de movimientos (SaaS)."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services import supabase_db
from app.services.finance_schema import finance_db_error, finance_db_ready
from app.services.user_id_utils import normalize_user_id

logger = logging.getLogger(__name__)

FINANCE_TZ_NAME = "America/New_York"
MAX_DESCRIPTION = 400
MAX_CATEGORY = 60
MAX_AMOUNT = 1_000_000_000
VALID_TYPES = ("ingreso", "gasto")
_DEDUP_WINDOW = timedelta(seconds=90)

# Períodos soportados en consultas/análisis por voz o chat.
PERIOD_LABELS: dict[str, str] = {
    "hoy": "hoy",
    "semana": "esta semana",
    "mes": "este mes",
    "mes_pasado": "el mes pasado",
    "anio": "este año",
    "todo": "todo el historial",
}


def _client():
    return supabase_db._client()


def _tz() -> ZoneInfo | None:
    try:
        return ZoneInfo(FINANCE_TZ_NAME)
    except Exception:  # noqa: BLE001 — tzdata puede faltar en dev
        return None


def _today() -> date:
    tz = _tz()
    return datetime.now(tz).date() if tz else datetime.now().date()


def today() -> date:
    """Fecha local del usuario (zona de finanzas)."""
    return _today()


_WEEKDAYS: dict[str, int] = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}


def resolve_due_date(text: str) -> date | None:
    """Convierte 'el lunes', 'mañana', 'hoy' o una fecha explícita en un date futuro."""
    t = (text or "").strip().lower()
    if not t:
        return None
    base = _today()
    if re.search(r"\bhoy\b", t):
        return base
    if re.search(r"\bma[nñ]ana\b", t):
        return base + timedelta(days=1)
    if re.search(r"pasado\s+ma[nñ]ana", t):
        return base + timedelta(days=2)
    for name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b{re.escape(name)}\b", t):
            delta = (weekday - base.weekday()) % 7
            if delta == 0:
                delta = 7  # el próximo, no hoy
            return base + timedelta(days=delta)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m", "%d-%m"):
        try:
            parsed = datetime.strptime(t, fmt).date()
            if fmt in ("%d/%m", "%d-%m"):
                parsed = parsed.replace(year=base.year)
                if parsed < base:
                    parsed = parsed.replace(year=base.year + 1)
            return parsed
        except ValueError:
            continue
    return None


def normalize_type(raw: str | None) -> str:
    t = (raw or "").strip().lower()
    if t in VALID_TYPES:
        return t
    if t in ("income", "ingresos", "entrada", "cobro", "cobré", "recibí", "gané"):
        return "ingreso"
    if t in ("expense", "gastos", "salida", "gasté", "pago", "compra"):
        return "gasto"
    raise ValueError("tipo debe ser 'ingreso' o 'gasto'")


def normalize_amount(raw: Any) -> float:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValueError("monto es obligatorio")
    try:
        value = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("monto inválido") from exc
    if value <= 0:
        raise ValueError("el monto debe ser mayor que cero")
    if value > MAX_AMOUNT:
        raise ValueError("monto fuera de rango")
    return round(value, 2)


def _parse_occurred_on(raw: Any) -> date:
    if not raw:
        return _today()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip().lower()
    today = _today()
    if text in ("", "hoy", "today"):
        return today
    if text in ("ayer", "yesterday"):
        return today - timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return today


def period_range(
    period: str | None,
    *,
    through_month_end: bool = False,
) -> tuple[date | None, date | None]:
    """Rango [desde, hasta] inclusivo para un período; (None, None) = todo."""
    key = (period or "mes").strip().lower()
    today = _today()
    if key in ("todo", "all", "historial", "siempre"):
        return None, None
    if key in ("hoy", "today", "dia", "día"):
        return today, today
    if key in ("semana", "week", "esta_semana"):
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6) if through_month_end else today
        return start, end
    if key in ("mes_pasado", "last_month", "mes pasado"):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if key in ("anio", "año", "year", "este_anio"):
        end = today.replace(month=12, day=31) if through_month_end else today
        return today.replace(month=1, day=1), end
    # default: este mes
    since = today.replace(day=1)
    if through_month_end:
        next_month = (since.replace(day=28) + timedelta(days=4)).replace(day=1)
        until = next_month - timedelta(days=1)
    else:
        until = today
    return since, until


def canonical_period(period: str | None) -> str:
    key = (period or "mes").strip().lower()
    mapping = {
        "hoy": "hoy", "today": "hoy", "dia": "hoy", "día": "hoy",
        "semana": "semana", "week": "semana", "esta_semana": "semana",
        "mes": "mes", "month": "mes", "este_mes": "mes",
        "mes_pasado": "mes_pasado", "last_month": "mes_pasado", "mes pasado": "mes_pasado",
        "anio": "anio", "año": "anio", "year": "anio", "este_anio": "anio",
        "todo": "todo", "all": "todo", "historial": "todo", "siempre": "todo",
    }
    return mapping.get(key, "mes")


def normalize_status(raw: str | None) -> str:
    s = (raw or "pagado").strip().lower()
    if s in ("pendiente", "pending", "programado", "por pagar"):
        return "pendiente"
    return "pagado"


def _parse_created_at(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        text = str(raw).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed
    except ValueError:
        return None


def _find_recent_duplicate(
    uid: str,
    *,
    kind: str,
    value: float,
    desc: str | None,
    state: str,
    due: date | None,
) -> dict[str, Any] | None:
    """Evita doble guardado por reintentos del frontend en la misma sesión."""
    try:
        query = (
            _client()
            .table("finance_transactions")
            .select(
                "id, amount, description, status, due_date, created_at, type, currency, category"
            )
            .eq("user_id", uid)
            .eq("type", kind)
            .eq("amount", value)
            .eq("status", state)
        )
        if desc:
            query = query.eq("description", desc)
        result = query.order("created_at", desc=True).limit(5).execute()
        cutoff = datetime.now(ZoneInfo("UTC")) - _DEDUP_WINDOW
        for row in result.data or []:
            if state == "pendiente" and due:
                row_due = row.get("due_date")
                if row_due and str(row_due)[:10] != due.isoformat():
                    continue
            created = _parse_created_at(row.get("created_at"))
            if created and created >= cutoff:
                return row
    except Exception as exc:  # noqa: BLE001
        logger.debug("[FINANCE] dedup check skipped: %s", exc)
    return None


def save_transaction(
    user_id: str,
    *,
    tx_type: str,
    amount: Any,
    category: str | None = None,
    description: str | None = None,
    occurred_on: Any = None,
    currency: str = "USD",
    status: str = "pagado",
    due_date: Any = None,
) -> dict[str, Any]:
    """Guarda un movimiento; devuelve {ok, id, ...} o {ok: False, error}."""
    if not finance_db_ready():
        schema_err = finance_db_error() or "Tabla finance_transactions no disponible."
        logger.warning("[FINANCE] save blocked — schema: %s", schema_err)
        return {"ok": False, "error": schema_err}

    uid = normalize_user_id(user_id)
    try:
        from app.services.supabase_db import ensure_profile

        ensure_profile(uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FINANCE] profile ensure skipped user=%s: %s", uid[:8], exc)

    kind = normalize_type(tx_type)
    value = normalize_amount(amount)
    day = _parse_occurred_on(occurred_on)
    cat = (category or "").strip()[:MAX_CATEGORY] or None
    desc = (description or "").strip()[:MAX_DESCRIPTION] or None
    cur = (currency or "USD").strip().upper()[:8] or "USD"
    state = normalize_status(status)

    due: date | None = None
    if state == "pendiente":
        if isinstance(due_date, date):
            due = due_date
        elif due_date:
            due = resolve_due_date(str(due_date))

    row: dict[str, Any] = {
        "user_id": uid,
        "type": kind,
        "amount": value,
        "currency": cur,
        "category": cat,
        "description": desc,
        "occurred_on": day.isoformat(),
        "status": state,
        "due_date": due.isoformat() if due else None,
    }
    dup = _find_recent_duplicate(
        uid,
        kind=kind,
        value=value,
        desc=desc,
        state=state,
        due=due,
    )
    if dup:
        logger.info("[FINANCE] dedup skip user=%s amount=%s status=%s", user_id[:8], value, state)
        return {
            "ok": True,
            "id": dup.get("id"),
            "type": kind,
            "amount": value,
            "currency": dup.get("currency", cur),
            "category": dup.get("category") or cat,
            "status": state,
            "due_date": dup.get("due_date"),
            "deduplicated": True,
        }
    try:
        result = _client().table("finance_transactions").insert(row).execute()
        saved = (result.data or [row])[0]
        try:
            supabase_db.log_ced_activity(
                uid,
                "finance_save",
                detail=f"{state}:{kind}:{value}",
                meta={"category": cat or "general"},
            )
        except Exception:  # noqa: BLE001
            pass
        logger.info(
            "[FINANCE] save user=%s type=%s amount=%s status=%s",
            user_id[:8], kind, value, state,
        )
        return {
            "ok": True,
            "id": saved.get("id"),
            "type": kind,
            "amount": value,
            "currency": cur,
            "category": cat,
            "occurred_on": day.isoformat(),
            "status": state,
            "due_date": due.isoformat() if due else None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[FINANCE] save failed user=%s", uid[:8])
        err_text = str(exc)
        if "PGRST205" in err_text or "Could not find the table" in err_text:
            return {
                "ok": False,
                "error": (
                    "Tabla finance_transactions no existe. "
                    "Ejecute migraciones 021 y 022 en Supabase."
                ),
            }
        if "violates foreign key" in err_text.lower() or "23503" in err_text:
            return {
                "ok": False,
                "error": "Perfil de usuario no encontrado en Supabase (profiles).",
            }
        return {"ok": False, "error": err_text[:200]}


def list_pending_payments(user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Pagos pendientes ordenados por fecha de vencimiento."""
    try:
        uid = normalize_user_id(user_id)
        result = (
            _client()
            .table("finance_transactions")
            .select("id, type, amount, currency, category, description, due_date, occurred_on")
            .eq("user_id", uid)
            .eq("status", "pendiente")
            .is_("deleted_at", "null")
            .order("due_date", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FINANCE] list pending failed %s", exc)
        return []


def mark_payment_paid(user_id: str, *, payment_id: str) -> dict[str, Any]:
    try:
        _client().table("finance_transactions").update(
            {"status": "pagado", "occurred_on": _today().isoformat()}
        ).eq("user_id", user_id).eq("id", payment_id).execute()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FINANCE] mark paid failed %s", exc)
        return {"ok": False}


def _fmt_money(value: float, currency: str = "USD") -> str:
    from app.services.finance_speech import amount_to_spoken_es

    return amount_to_spoken_es(value, currency)


def _fmt_due(due_raw: Any) -> str:
    from app.services.finance_speech import due_date_to_spoken_es, due_time_from_description

    # Compat: sin descripción aquí, solo fecha.
    return due_date_to_spoken_es(due_raw)


def format_pending_spoken(rows: list[dict[str, Any]], *, currency: str = "USD") -> str:
    from app.services.finance_speech import (
        amount_to_spoken_es,
        due_date_to_spoken_es,
        due_time_from_description,
    )

    if not rows:
        return "Señor, no tiene pagos pendientes registrados."
    total = 0.0
    parts: list[str] = []
    for r in rows[:8]:
        try:
            amt = float(r.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        total += amt
        cur = str(r.get("currency") or currency)
        cat = str(r.get("category") or "").strip()
        cat_txt = f" de {cat}" if cat else ""
        due_time = due_time_from_description(str(r.get("description") or ""))
        when = due_date_to_spoken_es(r.get("due_date"), due_time=due_time)
        parts.append(f"{amount_to_spoken_es(amt, cur)}{cat_txt} para {when}")
    joined = "; ".join(parts)
    return (
        f"Señor, tiene {len(rows)} pagos pendientes por "
        f"{amount_to_spoken_es(total, currency)}: {joined}."
    )


def list_transactions(
    user_id: str,
    *,
    since: date | None = None,
    until: date | None = None,
    status: str | None = "pagado",
    limit: int = 200,
) -> list[dict[str, Any]]:
    try:
        uid = normalize_user_id(user_id)

        def _run(*, hide_trashed: bool):
            query = (
                _client()
                .table("finance_transactions")
                .select(
                    "id, type, amount, currency, category, description, occurred_on, status"
                )
                .eq("user_id", uid)
            )
            if hide_trashed:
                query = query.is_("deleted_at", "null")
            if status is not None:
                query = query.eq("status", status)
            if since is not None:
                query = query.gte("occurred_on", since.isoformat())
            if until is not None:
                query = query.lte("occurred_on", until.isoformat())
            return (
                query.order("occurred_on", desc=True)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

        try:
            result = _run(hide_trashed=True)
        except Exception:  # noqa: BLE001
            result = _run(hide_trashed=False)
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FINANCE] list failed %s", exc)
        return []


def aggregate_transactions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Suma pura de movimientos — separada de la DB para test fácil."""
    total_ingreso = 0.0
    total_gasto = 0.0
    by_category: dict[str, float] = {}
    for row in rows:
        try:
            amount = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        kind = str(row.get("type") or "").lower()
        if kind == "ingreso":
            total_ingreso += amount
        elif kind == "gasto":
            total_gasto += amount
            cat = str(row.get("category") or "otros").lower()
            by_category[cat] = round(by_category.get(cat, 0.0) + amount, 2)
    total_ingreso = round(total_ingreso, 2)
    total_gasto = round(total_gasto, 2)
    top_categories = sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "count": len(rows),
        "total_ingreso": total_ingreso,
        "total_gasto": total_gasto,
        "balance": round(total_ingreso - total_gasto, 2),
        "by_category": dict(top_categories),
        "top_categories": top_categories[:5],
    }


def _parse_row_date(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def list_pending_in_period(
    user_id: str,
    *,
    since: date | None = None,
    until: date | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Pagos pendientes cuya due_date cae dentro del rango (incluye fechas futuras del mes)."""
    rows = list_pending_payments(user_id, limit=limit)
    if since is None and until is None:
        return rows
    filtered: list[dict[str, Any]] = []
    for row in rows:
        due = _parse_row_date(row.get("due_date") or row.get("occurred_on"))
        if due is None:
            continue
        if since is not None and due < since:
            continue
        if until is not None and due > until:
            continue
        filtered.append(row)
    return filtered


def summarize_finances(user_id: str, *, period: str | None = "mes") -> dict[str, Any]:
    canon = canonical_period(period)
    since, until = period_range(canon)
    _, until_pending = period_range(canon, through_month_end=True)
    rows = list_transactions(user_id, since=since, until=until, status="pagado", limit=500)
    summary = aggregate_transactions(rows)
    pending_rows = list_pending_in_period(
        user_id,
        since=since,
        until=until_pending,
    )
    pending_agg = aggregate_transactions(
        [{"type": "gasto", **row} for row in pending_rows]
    )
    summary["period"] = canon
    summary["period_label"] = PERIOD_LABELS.get(canon, "este mes")
    summary["pending_count"] = len(pending_rows)
    summary["pending_gasto"] = pending_agg.get("total_gasto", 0.0)
    summary["pending_rows"] = pending_rows
    return summary


def format_summary_spoken(summary: dict[str, Any], *, currency: str = "USD") -> str:
    """Resumen hablable/legible para voz o chat."""
    label = summary.get("period_label", "este mes")
    count = int(summary.get("count") or 0)
    pending_count = int(summary.get("pending_count") or 0)
    pending_gasto = float(summary.get("pending_gasto") or 0.0)
    pending_rows = summary.get("pending_rows") or []

    if not count and not pending_count:
        return (
            f"Señor, no tengo movimientos registrados para {label}. "
            "Dígame un gasto o ingreso y lo anoto."
        )

    parts: list[str] = []

    if count:
        ingreso = _fmt_money(summary.get("total_ingreso", 0.0), currency)
        gasto = _fmt_money(summary.get("total_gasto", 0.0), currency)
        balance = summary.get("balance", 0.0)
        balance_txt = _fmt_money(balance, currency)
        estado = "a favor" if balance >= 0 else "en déficit"
        parts.append(
            f"Señor, para {label}: ingresos {ingreso}, gastos {gasto}, "
            f"balance {balance_txt} {estado}."
        )
        top = summary.get("top_categories") or []
        if top:
            cats = ", ".join(f"{cat} {_fmt_money(amt, currency)}" for cat, amt in top[:3])
            parts.append(f"Mayores gastos: {cats}.")
    else:
        parts.append(f"Señor, no tiene gastos pagados registrados para {label}.")

    if pending_count:
        from app.services.finance_speech import (
            amount_to_spoken_es,
            due_date_to_spoken_es,
            due_time_from_description,
        )

        pend_parts: list[str] = []
        for row in pending_rows[:4]:
            try:
                amt = float(row.get("amount") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            due_time = due_time_from_description(str(row.get("description") or ""))
            when = due_date_to_spoken_es(row.get("due_date"), due_time=due_time)
            pend_parts.append(f"{amount_to_spoken_es(amt, currency)} para {when}")
        pend_joined = "; ".join(pend_parts)
        parts.append(
            f"Tiene {pending_count} pago(s) pendiente(s) en {label} "
            f"por {_fmt_money(pending_gasto, currency)}: {pend_joined}."
        )

    return " ".join(parts)
