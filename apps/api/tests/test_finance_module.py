"""Tests — módulo finanzas: detección de intent y parsing conversacional."""

from __future__ import annotations

from app.modules.finance_module import (
    is_finance_intent,
    is_finance_query_intent,
    is_finance_write_intent,
    parse_finance_statement,
)


def test_write_intent_expense():
    assert is_finance_write_intent("gasté 50 dólares en materiales hoy")
    assert is_finance_intent("gasté 50 dólares en materiales hoy")


def test_write_intent_income():
    assert is_finance_write_intent("recibí 800 dólares de un cliente")
    assert is_finance_intent("recibí 800 dólares de un cliente")


def test_write_intent_needs_amount():
    assert not is_finance_write_intent("gasté mucho en materiales")


def test_query_intent():
    assert is_finance_query_intent("cómo voy este mes")
    assert is_finance_query_intent("cuánto gasté esta semana")
    assert is_finance_query_intent("ayúdame a hacer un plan de ahorro")
    assert is_finance_query_intent("mis finanzas")


def test_non_finance_not_intent():
    assert not is_finance_intent("qué tengo mañana en el calendario")
    assert not is_finance_intent("hola cómo estás")
    assert not is_finance_write_intent("recuérdame comprar pan")


def test_parse_expense_with_category():
    parsed = parse_finance_statement("gasté 50 dólares en materiales hoy")
    assert parsed is not None
    assert parsed["type"] == "gasto"
    assert parsed["amount"] == "50"
    assert parsed["category"] == "materiales"
    assert parsed["occurred_on"] == "hoy"


def test_parse_income_with_source():
    parsed = parse_finance_statement("recibí 800 dólares de un cliente")
    assert parsed is not None
    assert parsed["type"] == "ingreso"
    assert parsed["amount"] == "800"
    assert parsed["category"] == "cliente"


def test_parse_amount_with_thousands():
    parsed = parse_finance_statement("pagué 1,200.50 en renta")
    assert parsed is not None
    assert parsed["type"] == "gasto"
    assert parsed["amount"] == "1200.50"
    assert parsed["category"] == "renta"


def test_parse_yesterday():
    parsed = parse_finance_statement("gasté 30 en comida ayer")
    assert parsed is not None
    assert parsed["occurred_on"] == "ayer"


def test_parse_no_amount_returns_none():
    assert parse_finance_statement("cómo van mis finanzas") is None


def test_handle_query_uses_summary(monkeypatch):
    import app.modules.finance_module as fm

    monkeypatch.setattr(
        fm,
        "summarize_finances",
        lambda user_id, period="mes": {
            "count": 2,
            "total_ingreso": 800.0,
            "total_gasto": 80.0,
            "balance": 720.0,
            "period_label": "este mes",
            "top_categories": [("materiales", 80.0)],
        },
    )
    out = fm.handle_finance_query_sync("user-1", "cómo voy este mes")
    assert "ingresos" in out["spoken"].lower()


def test_handle_write_saves(monkeypatch):
    import app.modules.finance_module as fm

    captured = {}

    def fake_save(user_id, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "type": kwargs["tx_type"], "amount": kwargs["amount"], "currency": "USD", "category": kwargs.get("category")}

    monkeypatch.setattr(fm, "save_transaction", fake_save)
    out = fm.handle_finance_query_sync("user-1", "gasté 50 dólares en materiales hoy")
    assert captured["tx_type"] == "gasto"
    assert "registré" in out["spoken"].lower() or "anoté" in out["spoken"].lower()
