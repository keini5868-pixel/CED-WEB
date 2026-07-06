"""Tests — HUD Life dashboard."""

from __future__ import annotations

from unittest.mock import patch

from app.services.hud_life import (
    build_life_connections,
    build_life_dashboard,
    build_life_dashboard_fallback,
    clean_life_text,
    check_calendar_token,
    check_gmail_token,
)


def test_build_life_connections_fast_path():
    with patch(
        "app.services.hud_life._calendar_section",
        return_value={"connected": True, "events": ["9:00 — Standup"], "hint": ""},
    ):
        with patch(
            "app.services.hud_life._gmail_section",
            return_value={"connected": False, "unread_count": 0, "messages": [], "hint": "Conecte Gmail"},
        ):
            data = build_life_connections("user-1")

    assert data["calendar"]["connected"] is True
    assert "Standup" in data["calendar"]["events"][0]
    assert "updated_at" in data
    assert "weather" not in data


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
    assert data["calendar"]["hint"] or data["calendar"]["connected"]
    assert data["gmail"]["hint"] or data["gmail"]["connected"]


def test_clean_life_text_removes_cite():
    raw = "[citeEn Charlotte, NC hoy hay 28°C[cite"
    cleaned = clean_life_text(raw)
    assert "[cite" not in cleaned.lower()
    assert "Charlotte" in cleaned


def test_calendar_connected_when_token_exists():
    from datetime import datetime, timezone

    with patch("app.services.hud_life.check_calendar_token", return_value=True):
        with patch(
            "app.services.google_oauth.get_valid_access_token",
            return_value="token",
        ):
            with patch(
                "app.services.google_calendar_api.resolve_window",
                return_value=(datetime.now(timezone.utc), datetime.now(timezone.utc)),
            ):
                with patch(
                    "app.services.google_calendar_api.list_events",
                    return_value=["9:00 AM — Reunión"],
                ):
                    from app.services.hud_life import _calendar_section

                    section = _calendar_section("user-1")
    assert section["connected"] is True
    assert "Reunión" in section["events"][0]


def test_universal_conversation_in_voice_and_chat_prompts():
    from app.domain.openai_voice_prompt import build_ced_voice_system_prompt
    from app.services.text_chat import CHAT_SYSTEM_BASE

    voice = build_ced_voice_system_prompt()
    assert "CONVERSACIÓN UNIVERSAL" in voice
    assert "no puedo hablar de eso" in voice.lower()
    assert "CONVERSACIÓN UNIVERSAL" in CHAT_SYSTEM_BASE
