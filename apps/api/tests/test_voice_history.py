"""Historial de voz en servidor, independiente del navegador."""

from __future__ import annotations


def test_persist_voice_turn_creates_conversation_and_appends(monkeypatch):
    bound: dict[str, str] = {}
    appended: list[tuple[str, str, str, str, str]] = []

    monkeypatch.setattr(
        "app.services.voice_client_session.get_conversation_id",
        lambda uid: bound.get(uid),
    )
    monkeypatch.setattr(
        "app.services.voice_client_session.set_conversation_id",
        lambda uid, cid: bound.__setitem__(uid, cid),
    )
    monkeypatch.setattr(
        "app.services.supabase_db.create_conversation",
        lambda uid: {"id": "conv-new"},
    )

    def fake_append(cid, uid, role, text, channel="voice"):
        appended.append((cid, uid, role, text, channel))

    monkeypatch.setattr("app.services.supabase_db.append_message", fake_append)

    from app.services.voice_history import persist_voice_turn

    persist_voice_turn("user-1", "user", "Hola CED")
    persist_voice_turn("user-1", "model", "Soy CED.")

    assert bound["user-1"] == "conv-new"
    assert appended == [
        ("conv-new", "user-1", "user", "Hola CED", "voice"),
        ("conv-new", "user-1", "model", "Soy CED.", "voice"),
    ]


def test_persist_voice_turn_skips_empty(monkeypatch):
    monkeypatch.setattr(
        "app.services.voice_client_session.get_conversation_id",
        lambda uid: "conv-1",
    )
    called = {"n": 0}

    def fake_append(*_args, **_kwargs):
        called["n"] += 1

    monkeypatch.setattr("app.services.supabase_db.append_message", fake_append)

    from app.services.voice_history import persist_voice_turn

    persist_voice_turn("user-1", "user", "   ")
    persist_voice_turn("", "user", "hola")
    assert called["n"] == 0
