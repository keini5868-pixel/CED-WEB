"""Tests — cierre de conversación de chat y memoria."""

from app.services.text_chat import TextChatError, end_text_conversation


def test_end_text_conversation_not_found(monkeypatch):
    monkeypatch.setattr(
        "app.services.text_chat.supabase_db.get_conversation",
        lambda _cid, _uid: None,
    )
    try:
        end_text_conversation("00000000-0000-0000-0000-000000000001", "conv-x")
        assert False, "expected TextChatError"
    except TextChatError as exc:
        assert exc.http_status == 404


def test_end_text_conversation_too_short(monkeypatch):
    monkeypatch.setattr(
        "app.services.text_chat.supabase_db.get_conversation",
        lambda _cid, _uid: {"id": "conv-1", "channel": "text", "created_at": "2026-07-04T10:00:00Z"},
    )
    monkeypatch.setattr(
        "app.services.text_chat.supabase_db.get_conversation_messages",
        lambda *_a, **_k: [],
    )
    out = end_text_conversation("user-1", "conv-1")
    assert out["ok"] is True
    assert out["saved"] is False


def test_end_text_conversation_finalizes(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr(
        "app.services.text_chat.supabase_db.get_conversation",
        lambda _cid, _uid: {"id": "conv-1", "channel": "text", "created_at": "2026-07-04T10:00:00Z"},
    )
    monkeypatch.setattr(
        "app.services.text_chat.supabase_db.get_conversation_messages",
        lambda *_a, **_k: [
            {"role": "user", "content": "Hola"},
            {"role": "model", "content": "A sus órdenes."},
        ],
    )

    def fake_finalize(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        "app.services.conversation_memory.finalize_session_async",
        fake_finalize,
    )

    out = end_text_conversation("user-1", "conv-1")
    assert out["saved"] is True
    assert calls and calls[0]["channel"] == "text"
    assert calls[0]["session_id"] == "conv-1"
