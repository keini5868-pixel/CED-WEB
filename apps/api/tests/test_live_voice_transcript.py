"""Puente de transcripción en vivo: custom LLM → client-state (Retell gateway no emite `update`)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app
from app.services import voice_client_session as vcs

UID = "550e8400-e29b-41d4-a716-446655440077"


def setup_function() -> None:
    vcs.end_voice_publish_session(UID)


def teardown_function() -> None:
    vcs.end_voice_publish_session(UID)


def test_set_live_transcript_grows_same_stream():
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
