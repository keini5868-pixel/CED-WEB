"""Finanzas personales — persistencia y agregación de movimientos (SaaS)."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.services import supabase_db

logger = logging.getLogger(__name__)

FINANCE_TZ_NAME = "America/New_York"
MAX_DESCRIPTION = 400
MAX_CATEGORY = 60
MAX_AMOUNT = 1_000_000_000
VALID_TYPES = ("ingreso", "gasto")

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


def period_range(period: str | None) -> tuple[date | None, date | None]:
    """Rango [desde, hasta] inclusivo para un período; (None, None) = todo."""
    key = (period or "mes").strip().lower()
    today = _today()
    if key in ("todo", "all", "historial", "siempre"):
        return None, None
    if key in ("hoy", "today", "dia", "día"):
        return today, today
    if key in ("semana", "week", "esta_semana"):
        start = today - timedelta(days=today.weekday())
        return start, today
    if key in ("mes_pasado", "last_month", "mes pasado"):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if key in ("anio", "año", "year", "este_anio"):
        return today.replace(month=1, day=1), today
    # default: este mes
    return today.replace(day=1), today


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
        "user_id": user_id,
        "type": kind,
        "amount": value,
        "currency": cur,
        "category": cat,
        "description": desc,
        "occurred_on": day.isoformat(),
        "status": state,
        "due_date": due.isoformat() if due else None,
    }
    try:
        result = _client().table("finance_transactions").insert(row).execute()
        saved = (result.data or [row])[0]
        try:
            supabase_db.log_ced_activity(
                user_id,
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
        logger.warning("[FINANCE] save failed %s", exc)
        return {
            "ok": False,
            "error": "Ejecute las migraciones 021 y 022 de finanzas en Supabase",
        }


def list_pending_payments(user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Pagos pendientes ordenados por fecha de vencimiento."""
    try:
        result = (
            _client()
            .table("finance_transactions")
            .select("id, type, amount, currency, category, description, due_date, occurred_on")
            .eq("user_id", user_id)
            .eq("status", "pendiente")
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


def _fmt_due(due_raw: Any) -> str:
    if not due_raw:
        return "sin fecha"
    try:
        d = due_raw if isinstance(due_raw, date) else datetime.strptime(str(due_raw), "%Y-%m-%d").date()
    except ValueError:
        return str(due_raw)
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return f"{dias[d.weekday()]} {d.day:02d}/{d.month:02d}"


def format_pending_spoken(rows: list[dict[str, Any]], *, currency: str = "USD") -> str:
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
        cat_txt = f" para {cat}" if cat else ""
        parts.append(f"{amt:,.2f} {cur}{cat_txt} el {_fmt_due(r.get('due_date'))}")
    joined = "; ".join(parts)
    return f"Señor, tiene {len(rows)} pagos pendientes por {total:,.2f} {currency}: {joined}."


def list_transactions(
    user_id: str,
    *,
    since: date | None = None,
    until: date | None = None,
    status: str | None = "pagado",
    limit: int = 200,
) -> list[dict[str, Any]]:
    try:
        query = (
            _client()
            .table("finance_transactions")
            .select("id, type, amount, currency, category, description, occurred_on, status")
            .eq("user_id", user_id)
        )
        if status is not None:
            query = query.eq("status", status)
        if since is not None:
            query = query.gte("occurred_on", since.isoformat())
        if until is not None:
            query = query.lte("occurred_on", until.isoformat())
        result = (
            query.order("occurred_on", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
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


def summarize_finances(user_id: str, *, period: str | None = "mes") -> dict[str, Any]:
    canon = canonical_period(period)
    since, until = period_range(canon)
    rows = list_transactions(user_id, since=since, until=until, status="pagado", limit=500)
    summary = aggregate_transactions(rows)
    summary["period"] = canon
    summary["period_label"] = PERIOD_LABELS.get(canon, "este mes")
    return summary


def _fmt_money(value: float, currency: str = "USD") -> str:
    return f"{value:,.2f} {currency}"


def format_summary_spoken(summary: dict[str, Any], *, currency: str = "USD") -> str:
    """Resumen hablable/legible para voz o chat."""
    label = summary.get("period_label", "este mes")
    if not summary.get("count"):
        return (
            f"Señor, no tengo movimientos registrados para {label}. "
            "Dígame un gasto o ingreso y lo anoto."
        )
    ingreso = _fmt_money(summary.get("total_ingreso", 0.0), currency)
    gasto = _fmt_money(summary.get("total_gasto", 0.0), currency)
    balance = summary.get("balance", 0.0)
    balance_txt = _fmt_money(balance, currency)
    estado = "a favor" if balance >= 0 else "en déficit"
    parts = [
        f"Señor, para {label}: ingresos {ingreso}, gastos {gasto}, "
        f"balance {balance_txt} {estado}."
    ]
    top = summary.get("top_categories") or []
    if top:
        cats = ", ".join(f"{cat} {_fmt_money(amt, currency)}" for cat, amt in top[:3])
        parts.append(f"Mayores gastos: {cats}.")
    return " ".join(parts)
