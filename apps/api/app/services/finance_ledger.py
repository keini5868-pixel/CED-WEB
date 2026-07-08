"""Finanzas personales — persistencia y agregación de movimientos (SaaS)."""

from __future__ import annotations

import logging
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


def save_transaction(
    user_id: str,
    *,
    tx_type: str,
    amount: Any,
    category: str | None = None,
    description: str | None = None,
    occurred_on: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Guarda un movimiento; devuelve {ok, id, ...} o {ok: False, error}."""
    kind = normalize_type(tx_type)
    value = normalize_amount(amount)
    day = _parse_occurred_on(occurred_on)
    cat = (category or "").strip()[:MAX_CATEGORY] or None
    desc = (description or "").strip()[:MAX_DESCRIPTION] or None
    cur = (currency or "USD").strip().upper()[:8] or "USD"

    row = {
        "user_id": user_id,
        "type": kind,
        "amount": value,
        "currency": cur,
        "category": cat,
        "description": desc,
        "occurred_on": day.isoformat(),
    }
    try:
        result = _client().table("finance_transactions").insert(row).execute()
        saved = (result.data or [row])[0]
        try:
            supabase_db.log_ced_activity(
                user_id,
                "finance_save",
                detail=f"{kind}:{value}",
                meta={"category": cat or "general"},
            )
        except Exception:  # noqa: BLE001
            pass
        logger.info("[FINANCE] save user=%s type=%s amount=%s", user_id[:8], kind, value)
        return {
            "ok": True,
            "id": saved.get("id"),
            "type": kind,
            "amount": value,
            "currency": cur,
            "category": cat,
            "occurred_on": day.isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[FINANCE] save failed %s", exc)
        return {
            "ok": False,
            "error": "Ejecute la migración 021_finance_transactions.sql en Supabase",
        }


def list_transactions(
    user_id: str,
    *,
    since: date | None = None,
    until: date | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    try:
        query = (
            _client()
            .table("finance_transactions")
            .select("id, type, amount, currency, category, description, occurred_on")
            .eq("user_id", user_id)
        )
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
    rows = list_transactions(user_id, since=since, until=until, limit=500)
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
