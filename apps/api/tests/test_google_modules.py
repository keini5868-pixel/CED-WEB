"""Tests — Google Calendar y Gmail modules."""

from __future__ import annotations

from unittest.mock import patch

from app.modules.calendar_module import CalendarModule, is_calendar_intent
from app.modules.gmail_module import GmailModule, is_gmail_intent
from app.services.ced_orchestrator import detect_module


def test_is_calendar_intent():
    assert is_calendar_intent("¿qué tengo mañana?")
    assert is_calendar_intent("agéndame una cita con el doctor")
    assert is_calendar_intent("¿qué eventos tengo esta semana?")
    assert not is_calendar_intent("hola")


def test_is_gmail_intent():
    assert is_gmail_intent("¿tengo emails importantes?")
    assert is_gmail_intent("léeme el email de JOMED")
    assert is_gmail_intent("envía un email a Marvin")
    assert not is_gmail_intent("hola")


def test_orchestrator_detects_calendar():
    assert detect_module("¿qué tengo mañana?", []) == "calendar"


def test_orchestrator_detects_gmail():
    assert detect_module("léeme el email de JOMED", []) == "gmail"


def test_calendar_module_not_connected():
    module = CalendarModule()

    async def run():
        with patch(
            "app.modules.calendar_module.get_valid_access_token",
            side_effect=ValueError("not_connected"),
        ):
            return await module.activate(
                "¿qué tengo mañana?",
                user_id="user-1",
                call_id="call-1",
                user_text="¿qué tengo mañana?",
            )

    import asyncio

    result = asyncio.run(run())
    assert result.handles_response
    assert "Calendar" in result.spoken


def test_gmail_module_lists_important():
    module = GmailModule()

    async def run():
        with patch(
            "app.modules.gmail_module.get_valid_access_token",
            return_value="token",
        ):
            with patch(
                "app.modules.gmail_module.list_messages",
                return_value=[
                    {"id": "1", "from": "a@x.com", "subject": "Urgente", "date": "", "snippet": ""},
                ],
            ):
                return await module.activate(
                    "¿tengo emails importantes?",
                    user_id="user-1",
                    call_id="call-1",
                    user_text="¿tengo emails importantes?",
                )

    import asyncio

    result = asyncio.run(run())
    assert result.ok
    assert "Urgente" in result.spoken
