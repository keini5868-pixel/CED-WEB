"""Tests — chat streaming endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app
from app.services.cognitive_router import route_message
from app.services.text_chat import (
    _can_stream_chat_text,
    _instant_chat_greeting_reply,
    iter_send_message_stream,
)

SAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"


def test_chat_stream_endpoint_returns_sse():
    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID

    def fake_stream(user_id, *, content, conversation_id=None):
        yield "event: token\ndata: {\"text\": \"Hola\"}\n\n"
        yield (
            "event: done\ndata: "
            "{\"conversation_id\": \"c1\", \"reply\": \"Hola\", "
            "\"usage\": {\"blocked\": false}}\n\n"
        )

    with patch("app.routers.chat.iter_send_message_stream", fake_stream):
        client = TestClient(app)
        res = client.post(
            "/v1/chat/send/stream",
            json={"content": "hola"},
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
    assert "event: token" in res.text
    assert "event: done" in res.text

    app.dependency_overrides.clear()


def test_instant_greeting_reply():
    assert _instant_chat_greeting_reply("hola") is not None
    assert _instant_chat_greeting_reply("cuéntame de marketing") is None


def test_can_stream_skips_live_web():
    assert _can_stream_chat_text("hola") is True
    assert _can_stream_chat_text("busca en internet las noticias de hoy") is False


def test_route_message_defer_skips_kb_search():
    with patch("app.services.cognitive_router.search_internal_knowledge") as kb:
        result = route_message(
            SAMPLE_UUID,
            "hola",
            channel="text",
            defer_enrichment=True,
        )
    kb.assert_not_called()
    assert result.intent == "direct_reply"
    assert result.meta.get("defer_enrichment") is True


def test_stream_greeting_yields_token_immediately():
    events: list[str] = []
    with (
        patch("app.services.text_chat.chat_status", return_value={"blocked": False}),
        patch("app.services.text_chat.supabase_db.get_profile", return_value={}),
        patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)),
        patch("app.deps.plan_access.chat_message_limit", return_value=100),
        patch("app.services.text_chat.get_settings") as settings,
        patch("app.services.text_chat.supabase_db.create_conversation", return_value={"id": "c1"}),
        patch("app.services.text_chat.supabase_db.get_conversation_messages", return_value=[]),
        patch("app.services.text_chat.supabase_db.append_message"),
        patch("app.services.text_chat.route_message") as route,
    ):
        settings.return_value = MagicMock(
            google_api_key="gk",
            anthropic_api_key="ak",
            gemini_voice_model="gemini-2.5-flash",
        )
        route.side_effect = AssertionError("route_message no debe llamarse en saludo instantáneo")
        for chunk in iter_send_message_stream(SAMPLE_UUID, content="hola"):
            events.append(chunk)
    assert any("event: token" in e for e in events)
    assert any("event: done" in e for e in events)
