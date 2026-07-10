"""Tests — pipeline unificado y contexto por módulo."""

from __future__ import annotations

from app.services.chat_module_context import (
    fetch_module_stream_context,
    requires_sync_module_handler,
)


def test_calendar_query_is_streamable():
    assert not requires_sync_module_handler("qué tengo mañana en el calendario")


def test_calendar_create_requires_sync():
    assert requires_sync_module_handler("agéndame una cita mañana a las 3pm")


def test_finance_write_requires_sync():
    assert requires_sync_module_handler("gasté 50 dólares en materiales hoy")


def test_reminder_create_requires_sync():
    assert requires_sync_module_handler("recuérdame comprar pan mañana")


def test_calendar_context_fetch(monkeypatch):
    monkeypatch.setattr(
        "app.modules.calendar_module.handle_calendar_query_sync",
        lambda _uid, _text: {"spoken": "Mañana tiene reunión a las 10."},
    )
    ctx, meta = fetch_module_stream_context("u1", "qué tengo mañana")
    assert ctx and "reunión" in ctx
    assert meta and meta.get("intent") == "calendar"


def test_weather_context_fetch(monkeypatch):
    monkeypatch.setattr(
        "app.services.gemini_grounded.execute_search_web_sync",
        lambda _q, kind="general": {
            "context_for_llm": "Santo Domingo: 32°C, soleado.",
            "spoken": "Hace calor.",
        },
    )
    ctx, meta = fetch_module_stream_context("u1", "cómo está el clima hoy")
    assert ctx and "32°C" in ctx
    assert meta and meta.get("intent") == "weather"
