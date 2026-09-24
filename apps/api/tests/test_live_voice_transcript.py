"""Puente de transcripción en vivo: custom LLM → client-state (Retell gateway no emite `update`)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app
from app.routers.retell_custom_llm import latest_transcript_line
from app.services import voice_client_session as vcs

UID = "550e8400-e29b-41d4-a716-446655440077"


def setup_function() -> None:
    vcs.end_voice_publish_session(UID)


def teardown_function() -> None:
    vcs.end_voice_publish_session(UID)


def test_latest_transcript_line_picks_last_agent():
    tx = [
        {"role": "agent", "content": "Hola"},
        {"role": "user", "content": "qué hora es"},
        {"role": "agent", "content": "Son las diez, señor."},
    ]
    assert latest_transcript_line(tx, "agent") == "Son las diez, señor."
    assert latest_transcript_line(tx, "user") == "qué hora es"
    first = vcs.set_live_transcript(
        UID,
        role="model",
        text="CED en línea",
        stream_key="agent-1",
        partial=True,
    )
    second = vcs.set_live_transcript(
        UID,
        role="model",
        text="CED en línea, señor.",
        stream_key="agent-1",
        partial=True,
    )
    assert first is not None and second is not None
    assert second["seq"] > first["seq"]
    state = vcs.get_state(UID)
    row = state["live_transcript"]
    assert row["text"] == "CED en línea, señor."
    assert row["stream_key"] == "agent-1"
    assert row["partial"] is True
    assert row["role"] == "model"


def test_client_state_transcript_turns_from_db(monkeypatch):
    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: UID

    def fake_recent(user_id: str, conversation_id: str | None = None, **kwargs):
        assert user_id == UID
        return (
            [
                {
                    "id": "m1",
                    "role": "user",
                    "content": "qué hora es",
                    "created_at": "2026-09-24T03:00:00Z",
                }
            ],
            "conv-live",
        )

    monkeypatch.setattr(
        "app.routers.voice_client.supabase_db.recent_session_messages",
        fake_recent,
    )
    client = TestClient(app)
    res = client.get("/v1/voice/client-state?transcript=true")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["conversation_id"] == "conv-live"
    assert data["transcript_turns"][0]["content"] == "qué hora es"


def test_set_live_transcript_skips_identical_snapshot():
    vcs.set_live_transcript(UID, role="user", text="hola", stream_key="user-2", partial=False)
    a = vcs.get_state(UID)["live_transcript"]
    vcs.set_live_transcript(UID, role="user", text="hola", stream_key="user-2", partial=False)
    b = vcs.get_state(UID)["live_transcript"]
    assert a["seq"] == b["seq"]


def test_client_state_http_exposes_live_transcript():
    vcs.set_live_transcript(
        UID,
        role="model",
        text="Listo, señor.",
        stream_key="agent-9",
        partial=False,
    )
    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: UID
    client = TestClient(app)
    res = client.get("/v1/voice/client-state")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["live_transcript"]["text"] == "Listo, señor."
    assert data["live_transcript"]["stream_key"] == "agent-9"
    assert data["live_transcript"]["role"] == "model"


def test_resolve_call_conversation_from_metadata():
    from app.services.retell_call_registry import (
        bind_call_user,
        release_call_user,
        resolve_call_conversation,
        resolve_call_user,
    )

    call_id = "call-conv-live-1"
    release_call_user(call_id)
    uid = resolve_call_user(
        call_id,
        {
            "call": {
                "metadata": {
                    "user_id": UID,
                    "conversation_id": "conv-abc",
                }
            }
        },
    )
    assert uid == UID
    assert resolve_call_conversation(call_id) == "conv-abc"
    release_call_user(call_id)
