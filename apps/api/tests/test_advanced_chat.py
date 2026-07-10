"""Tests — Modo Avanzado aislado (advanced_mode)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app
import app.services.advanced_mode.service as adv

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
    with patch("app.services.advanced_mode.claude_stream.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(anthropic_api_key="")
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


def test_advanced_status_anthropic_only():
    with patch("app.services.advanced_mode.claude_stream.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(anthropic_api_key="sk-test")
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
    assert body["anthropic_configured"] is True
    app.dependency_overrides.clear()


def test_advanced_instant_datetime_reply():
    from app.services.system_clock import try_instant_datetime_reply

    reply = try_instant_datetime_reply("qué día es hoy")
    assert reply
    assert "tool_code" not in reply.lower()
    assert "Hoy es" in reply


def test_advanced_needs_tools_for_web_research():
    from app.services.advanced_mode.intents import needs_advanced_full_pipeline

    assert needs_advanced_full_pipeline(
        "últimas noticias de Venezuela hoy",
        [],
    )


def test_advanced_streams_business_query_without_tools():
    from app.services.advanced_mode.intents import needs_advanced_full_pipeline

    assert not needs_advanced_full_pipeline(
        "Resume las ventajas de automatizar marketing digital",
        [],
    )
    assert not needs_advanced_full_pipeline(
        "dame información sobre estrategia de ventas",
        [],
    )


def test_advanced_stream_greeting_hola_yields_token_immediately():
    events = list(adv.iter_advanced_message_stream("u1", message="HOLA", history=[]))
    token_events = [ev for ev in events if ev.startswith("event: token")]
    assert token_events, "expected instant greeting token"
    done = _collect_done(events)
    assert "modo avanzado" in done["response"].lower()


def test_advanced_stream_duplicate_hola_replays_cached():
    events_first = list(adv.iter_advanced_message_stream("u1", message="hola", history=[]))
    token_first = [e for e in events_first if e.startswith("event: token")]
    assert token_first, "expected greeting token"

    events_second = list(adv.iter_advanced_message_stream("u1", message="hola", history=[]))
    token_second = [e for e in events_second if e.startswith("event: token")]
    assert token_second, "duplicate should replay cached greeting"


def test_advanced_stream_fallback_yields_token_before_done(monkeypatch):
    """Si el stream LLM falla, el fallback debe emitir token antes de done."""

    def fake_stream(*args, **kwargs):
        raise RuntimeError("stream down")

    monkeypatch.setattr(
        "app.services.advanced_mode.service.iter_advanced_claude_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        adv,
        "_stream_fallback_reply",
        lambda **kwargs: "Análisis listo, señor.",
    )
    monkeypatch.setattr(
        "app.services.advanced_mode.service.require_anthropic_api_key",
        lambda: "anthropic-key",
    )

    events = list(
        adv.iter_advanced_message_stream(
            "u1",
            message="Resume las ventajas de automatizar marketing.",
            history=[],
        )
    )
    token_events = [ev for ev in events if ev.startswith("event: token")]
    assert token_events, "expected token before done on advanced fallback"
    done = _collect_done(events)
    assert "análisis" in done["response"].lower()
