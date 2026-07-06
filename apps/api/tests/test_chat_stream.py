"""Tests — chat streaming endpoint."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app

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
