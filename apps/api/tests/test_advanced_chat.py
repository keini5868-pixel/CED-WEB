"""Tests — chat avanzado Claude."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app
import app.services.claude_advanced as adv

SAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"


def _collect_done(events: list[str]) -> dict:
    for ev in events:
        if ev.startswith("event: done"):
            data_line = [ln for ln in ev.splitlines() if ln.startswith("data: ")][0]
            return json.loads(data_line[6:])
    raise AssertionError("no done event")


def test_advanced_chat_endpoint():
    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID

    def fake_send(user_id, *, message, history, conversation_id=None):
        return {
            "response": f"Análisis de: {message}",
            "model": "claude-sonnet-4-6",
        }

    with patch("app.routers.advanced_chat.send_advanced_message", fake_send):
        client = TestClient(app)
        res = client.post(
            "/v1/advanced/chat",
            json={"message": "estrategia de ventas", "history": []},
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    body = res.json()
    assert "estrategia" in body["response"]
    assert body["model"] == "claude-sonnet-4-6"

    app.dependency_overrides.clear()


def test_advanced_status_missing_key():
    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            anthropic_api_key="",
            google_api_key="",
        )
        from app.config import get_settings

        get_settings.cache_clear()
        app = create_app()
        app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID
        client = TestClient(app)
        res = client.get(
            "/v1/advanced/status",
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    assert res.json()["configured"] is False
    app.dependency_overrides.clear()


def test_advanced_status_google_only():
    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            anthropic_api_key="",
            google_api_key="gk-test",
        )
        from app.config import get_settings

        get_settings.cache_clear()
        app = create_app()
        app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID
        client = TestClient(app)
        res = client.get(
            "/v1/advanced/status",
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is True
    assert body["google_configured"] is True
    app.dependency_overrides.clear()


def test_advanced_instant_datetime_reply():
    from app.services.claude_advanced import _try_instant_datetime_reply

    reply = _try_instant_datetime_reply("qué día es hoy")
    assert reply
    assert "tool_code" not in reply.lower()
    assert "Hoy es" in reply


def test_advanced_recovers_stream_tool_code():
    from app.services.claude_advanced import _recover_advanced_reply

    hallucinated = (
        "Un momento, señor.\n\n**tool_code**\n"
        'print(search_web(query="qué día es hoy"))'
    )
    with patch(
        "app.services.claude_advanced._resolve_hallucinated_tool_code_reply",
        return_value="Hoy es martes 7 de julio de 2026, señor.",
    ):
        fixed = _recover_advanced_reply(
            "user-1",
            hallucinated,
            text="qué día es hoy",
            history=[],
            conversation_id="adv-1",
        )
    assert "tool_code" not in fixed.lower()
    assert "print(" not in fixed.lower()


def test_advanced_needs_tools_for_web_research():
    from app.services.claude_advanced import _needs_advanced_tools

    assert _needs_advanced_tools(
        "últimas noticias de Venezuela hoy",
        [],
    )


def test_advanced_stream_greeting_hola_yields_token_immediately():
    events = list(adv.iter_advanced_message_stream("u1", message="HOLA", history=[]))
    token_events = [ev for ev in events if ev.startswith("event: token")]
    assert token_events, "expected instant greeting token"
    done = _collect_done(events)
    assert "modo avanzado" in done["response"].lower()
