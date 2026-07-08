"""Tests aislados — memoria modular on-demand (Fase 2 v2)."""

from __future__ import annotations

from unittest.mock import patch

from app.services.module_memory import (
    MEMORY_LOADERS,
    MODULES_WITH_MEMORY,
    format_module_context,
    has_module_memory,
    load_module_memory,
)


def test_registry_covers_expected_modules():
    assert "finance" in MEMORY_LOADERS
    assert "calendar" in MEMORY_LOADERS
    assert "gmail" in MEMORY_LOADERS
    assert "memory" in MEMORY_LOADERS
    assert MODULES_WITH_MEMORY <= frozenset(MEMORY_LOADERS.keys())


def test_has_module_memory():
    assert has_module_memory("finance") is True
    assert has_module_memory("map") is False


def test_load_finance_memory_mocked():
    fake_summary = {"count": 2, "total_gastos": 100, "total_ingresos": 500, "balance": 400}
    with patch("app.services.finance_ledger.summarize_finances", return_value=fake_summary), patch(
        "app.services.finance_ledger.format_summary_spoken",
        return_value="Este mes: balance positivo.",
    ), patch("app.services.finance_ledger.list_pending_payments", return_value=[]):
        block = load_module_memory("finance", "00000000-0000-0000-0000-000000000001")
    assert block is not None
    assert "MEMORIA FINANZAS" in block
    assert "balance positivo" in block


def test_load_gmail_not_connected():
    with patch(
        "app.services.google_oauth.get_connection_status",
        return_value={"connected": False},
    ):
        block = load_module_memory("gmail", "user-1")
    assert block is not None
    assert "no conectado" in block.lower()


def test_load_calendar_connected_with_events():
    with patch(
        "app.services.google_calendar_api.get_calendar_events",
        return_value={
            "connected": True,
            "today_events": [{"display": "Reunión 10:00"}],
            "week_events": [],
        },
    ):
        block = load_module_memory("calendar", "user-1")
    assert block is not None
    assert "Reunión 10:00" in block


def test_load_unknown_module_returns_none():
    assert load_module_memory("map", "user-1") is None
    assert load_module_memory("finance", "") is None


def test_format_module_context():
    wrapped = format_module_context("finance", "datos reales")
    assert wrapped is not None
    assert "CONTEXTO MÓDULO FINANCE" in wrapped
    assert "datos reales" in wrapped
