"""Lista de chats: preview en lote, sin N+1."""

from __future__ import annotations


def test_list_conversations_filtered_batches_messages(monkeypatch):
    from app.services import supabase_db

    monkeypatch.setattr(
        supabase_db,
        "list_conversations",
        lambda *a, **k: [
            {
                "id": "c1",
                "title": "Hilo",
                "channel": "text",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-02",
            }
        ],
    )
    monkeypatch.setattr(
        supabase_db,
        "list_messages_for_conversations",
        lambda ids, per_conversation=8: {
            "c1": [
                {"content": "hola", "role": "user"},
                {"content": "respuesta", "role": "model"},
            ]
        },
    )

    rows = supabase_db.list_conversations_filtered("user-1", include_messages=True)
    assert len(rows) == 1
    assert rows[0]["preview"] == "respuesta"
    assert rows[0]["message_count"] == 2
    assert rows[0]["messages"][0]["content"] == "hola"


def test_list_conversations_filtered_falls_back_to_title(monkeypatch):
    from app.services import supabase_db

    monkeypatch.setattr(
        supabase_db,
        "list_conversations",
        lambda *a, **k: [
            {
                "id": "c2",
                "title": "FitLine",
                "channel": "voice",
                "created_at": "",
                "updated_at": "",
            }
        ],
    )
    monkeypatch.setattr(
        supabase_db,
        "list_messages_for_conversations",
        lambda ids, per_conversation=8: {"c2": []},
    )

    rows = supabase_db.list_conversations_filtered("user-1")
    assert rows[0]["preview"] == "FitLine"
    assert "messages" not in rows[0]
