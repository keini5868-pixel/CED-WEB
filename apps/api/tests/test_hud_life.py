"""Tests — HUD Life dashboard."""

from __future__ import annotations

from unittest.mock import patch

from app.services.hud_life import build_life_dashboard, build_life_dashboard_fallback


def test_build_life_dashboard_structure():
    with patch(
        "app.services.hud_life._web_lines",
        side_effect=[
            ["28°C · Despejado", "Humedad 65%"],
            ["Buena · Índice 42"],
            ["Árbol: Bajo · Pasto: Moderado"],
        ],
    ):
        with patch("app.services.hud_life._calendar_section", return_value={"connected": False, "events": [], "hint": "Conecte Calendar"}):
            with patch(
                "app.services.hud_life._gmail_section",
                return_value={"connected": False, "unread_count": 0, "messages": [], "hint": "Conecte Gmail"},
            ):
                data = build_life_dashboard("user-1")

    assert "date_label" in data
    assert data["weather"]["lines"][0].startswith("28")
    assert data["air_quality"]["lines"][0].startswith("Buena")
    assert data["pollen"]["lines"][0].startswith("Árbol")
    assert data["calendar"]["hint"]


def test_build_life_dashboard_fallback_always_has_date():
    data = build_life_dashboard_fallback("user-1")
    assert data["date_label"]
    assert data["weather"]["lines"]
    assert data["calendar"]["hint"]
    assert data["gmail"]["hint"]


def test_universal_conversation_in_voice_and_chat_prompts():
    from app.domain.openai_voice_prompt import build_ced_voice_system_prompt
    from app.services.text_chat import CHAT_SYSTEM_BASE

    voice = build_ced_voice_system_prompt()
    assert "CONVERSACIÓN UNIVERSAL" in voice
    assert "no puedo hablar de eso" in voice.lower()
    assert "CONVERSACIÓN UNIVERSAL" in CHAT_SYSTEM_BASE
