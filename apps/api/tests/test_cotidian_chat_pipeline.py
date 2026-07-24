"""Tests — pipeline unificado y contexto por módulo."""

from __future__ import annotations

from app.services.chat_module_context import (
    fetch_module_stream_context,
    requires_sync_module_handler,
)




def test_finance_write_requires_sync():
    assert requires_sync_module_handler("gasté 50 dólares en materiales hoy")


def test_reminder_create_requires_sync():
    assert requires_sync_module_handler("recuérdame comprar pan mañana")



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
