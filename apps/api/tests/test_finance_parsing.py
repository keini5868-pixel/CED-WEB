"""Tests de parsing conversacional de finanzas (montos, pagos pendientes).

Regresiones reportadas por el usuario en voz:
  - "1000" se guardaba como "100" (regex de monto recortaba un dígito).
  - "tengo que tener 1000 para el viernes" no se reconocía como pago pendiente.
  - la categoría capturaba expresiones de tiempo ("día de la semana que viene").
  - el separador de miles "1,200" se partía en "1" + "200".
"""

from __future__ import annotations

from app.modules.finance_module import (
    is_finance_intent,
    is_finance_pending_write,
    parse_finance_statement,
    parse_pending_statements,
)


def test_amount_1000_not_truncated():
    parsed = parse_finance_statement("gasté 1000 dólares en materiales")
    assert parsed is not None
    assert parsed["amount"] == "1000"


def test_pending_tener_recognized():
    text = "tengo que tener 1000 dólares para el viernes"
    assert is_finance_intent(text) is True
    assert is_finance_pending_write(text) is True
    rows = parse_pending_statements(text)
    assert len(rows) == 1
    assert rows[0]["amount"] == "1000"


def test_pending_temporal_not_taken_as_category():
    rows = parse_pending_statements(
        "tengo que tener 1000 dólares para el día viernes de la semana que viene"
    )
    assert len(rows) == 1
    assert rows[0]["amount"] == "1000"
    assert rows[0]["category"] is None


def test_pending_multiple_payments():
    rows = parse_pending_statements(
        "el lunes tengo que pagar 850, el miércoles 300 para el mercado"
    )
    assert len(rows) == 2
    assert rows[0]["amount"] == "850"
    assert rows[1]["amount"] == "300"
    assert rows[1]["category"] == "mercado"


def test_thousands_separator_not_split():
    rows = parse_pending_statements("tengo que pagar 1,200 el viernes")
    assert len(rows) == 1
    assert rows[0]["amount"] == "1200"


def test_income_decimal_amount():
    parsed = parse_finance_statement("recibí 1,200.50 de un cliente")
    assert parsed is not None
    assert parsed["type"] == "ingreso"
    assert parsed["amount"] == "1200.50"
