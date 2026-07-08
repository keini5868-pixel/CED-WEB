"""Tests — tools de voz de finanzas: declaración y dispatch."""

from __future__ import annotations

import asyncio

from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS
from app.services.voice_tool_executor import execute_voice_tool


def _tool_names() -> set[str]:
    return {t.get("name") for t in OPENAI_REALTIME_TOOLS}


def test_finance_tools_declared():
    names = _tool_names()
    assert "registrar_movimiento_financiero" in names
    assert "consultar_finanzas" in names


def test_register_tool_required_params():
    tool = next(
        t for t in OPENAI_REALTIME_TOOLS if t["name"] == "registrar_movimiento_financiero"
    )
    assert tool["parameters"]["required"] == ["tipo", "monto"]


def test_dispatch_registrar_movimiento(monkeypatch):
    captured = {}

    def fake_save(user_id, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "type": kwargs["tx_type"],
            "amount": kwargs["amount"],
            "currency": "USD",
            "category": kwargs.get("category"),
        }

    monkeypatch.setattr("app.services.finance_ledger.save_transaction", fake_save)

    result = asyncio.run(
        execute_voice_tool(
            "registrar_movimiento_financiero",
            "user-fin",
            {"tipo": "gasto", "monto": 50, "categoria": "materiales"},
        )
    )
    assert result.get("ok") is not False
    assert captured["tx_type"] == "gasto"
    assert captured["amount"] == 50
    assert "materiales" in result.get("spoken", "").lower()


def test_dispatch_consultar_finanzas(monkeypatch):
    monkeypatch.setattr(
        "app.services.finance_ledger.summarize_finances",
        lambda user_id, period="mes": {
            "count": 2,
            "total_ingreso": 800.0,
            "total_gasto": 80.0,
            "balance": 720.0,
            "period": "mes",
            "period_label": "este mes",
            "top_categories": [("materiales", 80.0)],
        },
    )

    result = asyncio.run(
        execute_voice_tool("consultar_finanzas", "user-fin", {"periodo": "mes"})
    )
    assert result.get("ok") is not False
    assert "ingresos" in result.get("spoken", "").lower()
    assert result.get("summary", {}).get("balance") == 720.0


def test_dispatch_registrar_invalid_amount(monkeypatch):
    def fake_save(user_id, **kwargs):
        raise ValueError("el monto debe ser mayor que cero")

    monkeypatch.setattr("app.services.finance_ledger.save_transaction", fake_save)

    result = asyncio.run(
        execute_voice_tool(
            "registrar_movimiento_financiero",
            "user-fin",
            {"tipo": "gasto", "monto": 0},
        )
    )
    assert result.get("ok") is False
    assert result.get("error") == "finance_invalid"
