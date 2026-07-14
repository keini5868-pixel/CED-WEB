"""Tests — finanzas: normalización, agregación y resumen (funciones puras)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.finance_ledger import (
    aggregate_transactions,
    canonical_period,
    format_pending_spoken,
    format_summary_spoken,
    normalize_amount,
    normalize_status,
    normalize_type,
    period_range,
    resolve_due_date,
    today,
)


def test_normalize_type_variants():
    assert normalize_type("gasto") == "gasto"
    assert normalize_type("ingreso") == "ingreso"
    assert normalize_type("gasté") == "gasto"
    assert normalize_type("recibí") == "ingreso"
    with pytest.raises(ValueError):
        normalize_type("otro")


def test_normalize_amount_parses_and_validates():
    assert normalize_amount("50") == 50.0
    assert normalize_amount("1,200.50") == 1200.5
    assert normalize_amount(800) == 800.0
    with pytest.raises(ValueError):
        normalize_amount(0)
    with pytest.raises(ValueError):
        normalize_amount("gratis")
    with pytest.raises(ValueError):
        normalize_amount(None)


def test_period_range_month_includes_today():
    since, until = period_range("mes")
    assert since is not None and until is not None
    assert since.day == 1
    assert until >= since


def test_period_range_all_is_open():
    assert period_range("todo") == (None, None)


def test_period_range_today():
    since, until = period_range("hoy")
    assert since == until


def test_canonical_period_maps_aliases():
    assert canonical_period("month") == "mes"
    assert canonical_period("last_month") == "mes_pasado"
    assert canonical_period("week") == "semana"
    assert canonical_period("desconocido") == "mes"


def test_aggregate_transactions_totals_and_categories():
    rows = [
        {"type": "ingreso", "amount": 800, "category": "cliente"},
        {"type": "gasto", "amount": 50, "category": "materiales"},
        {"type": "gasto", "amount": 30, "category": "materiales"},
        {"type": "gasto", "amount": 20, "category": "comida"},
    ]
    agg = aggregate_transactions(rows)
    assert agg["total_ingreso"] == 800.0
    assert agg["total_gasto"] == 100.0
    assert agg["balance"] == 700.0
    assert agg["by_category"]["materiales"] == 80.0
    assert agg["top_categories"][0] == ("materiales", 80.0)


def test_aggregate_ignores_bad_rows():
    rows = [
        {"type": "gasto", "amount": "nan-ish"},
        {"type": "ingreso", "amount": None},
        {"type": "gasto", "amount": 10, "category": "x"},
    ]
    agg = aggregate_transactions(rows)
    assert agg["total_gasto"] == 10.0
    assert agg["total_ingreso"] == 0.0


def test_format_summary_spoken_empty():
    summary = {"count": 0, "period_label": "este mes", "pending_count": 0}
    text = format_summary_spoken(summary)
    assert "no tengo movimientos" in text.lower()


def test_format_summary_spoken_pending_only():
    summary = {
        "count": 0,
        "period_label": "este mes",
        "pending_count": 1,
        "pending_gasto": 300.0,
        "pending_rows": [
            {"amount": 300, "currency": "USD", "due_date": "2026-07-10"},
        ],
    }
    text = format_summary_spoken(summary)
    assert "pendiente" in text.lower()
    assert "trescientos" in text
    assert "no tiene gastos pagados" in text.lower()


def test_list_pending_in_period_filters_by_due_date():
    from app.services.finance_ledger import list_pending_in_period

    rows = [
        {"amount": 300, "due_date": "2026-07-10", "status": "pendiente"},
        {"amount": 50, "due_date": "2026-08-01", "status": "pendiente"},
    ]

    def fake_list(user_id, limit=50):
        return rows

    import app.services.finance_ledger as fl

    orig = fl.list_pending_payments
    fl.list_pending_payments = fake_list
    try:
        since = date(2026, 7, 1)
        until = date(2026, 7, 31)
        filtered = list_pending_in_period("u1", since=since, until=until)
        assert len(filtered) == 1
        assert filtered[0]["amount"] == 300
    finally:
        fl.list_pending_payments = orig


def test_format_summary_spoken_with_data():
    summary = {
        "count": 3,
        "total_ingreso": 800.0,
        "total_gasto": 100.0,
        "balance": 700.0,
        "period_label": "este mes",
        "top_categories": [("materiales", 80.0), ("comida", 20.0)],
    }
    text = format_summary_spoken(summary)
    assert "ingresos" in text.lower()
    assert "balance" in text.lower()
    assert "materiales" in text.lower()
    assert "a favor" in text.lower()


def test_normalize_status():
    assert normalize_status("pendiente") == "pendiente"
    assert normalize_status("por pagar") == "pendiente"
    assert normalize_status(None) == "pagado"
    assert normalize_status("pagado") == "pagado"
    assert normalize_status("cualquiera") == "pagado"


def test_resolve_due_date_relative():
    base = today()
    assert resolve_due_date("hoy") == base
    assert resolve_due_date("mañana") == base + timedelta(days=1)
    lunes = resolve_due_date("lunes")
    assert lunes is not None and lunes.weekday() == 0 and lunes > base
    assert resolve_due_date("") is None
    assert resolve_due_date("cualquier cosa") is None


def test_format_pending_spoken_empty():
    assert "no tiene pagos pendientes" in format_pending_spoken([]).lower()


def test_format_pending_spoken_with_rows():
    rows = [
        {"amount": 850, "currency": "USD", "category": None, "due_date": "2026-07-13"},
        {"amount": 300, "currency": "USD", "category": "mercado", "due_date": "2026-07-10"},
    ]
    text = format_pending_spoken(rows)
    assert "2 pagos pendientes" in text
    assert "mil ciento cincuenta" in text
    assert "mercado" in text


def test_format_summary_spoken_deficit():
    summary = {
        "count": 1,
        "total_ingreso": 10.0,
        "total_gasto": 100.0,
        "balance": -90.0,
        "period_label": "este mes",
        "top_categories": [("renta", 100.0)],
    }
    text = format_summary_spoken(summary)
    assert "déficit" in text.lower()
