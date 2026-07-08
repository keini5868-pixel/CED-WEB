"""Tests — finanzas: normalización, agregación y resumen (funciones puras)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.finance_ledger import (
    aggregate_transactions,
    canonical_period,
    format_summary_spoken,
    normalize_amount,
    normalize_type,
    period_range,
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
    summary = {"count": 0, "period_label": "este mes"}
    text = format_summary_spoken(summary)
    assert "no tengo movimientos" in text.lower()


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
