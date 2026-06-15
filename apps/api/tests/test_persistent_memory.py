"""Tests — memoria persistente y conocimiento viral."""

from app.domain.ced_viral_knowledge import CED_VIRAL_KNOWLEDGE_2026
from app.services.chat_intents import is_generate_image_intent
from app.services.conversation_memory import (
    format_recall_for_voice,
    load_user_context,
)


def test_viral_knowledge_contains_instagram_2026():
    assert "sends per reach" in CED_VIRAL_KNOWLEDGE_2026.lower()
    assert "jueves" in CED_VIRAL_KNOWLEDGE_2026.lower()
    assert "reels" in CED_VIRAL_KNOWLEDGE_2026.lower()


def test_viral_knowledge_contains_hooks():
    assert "primeros 3 segundos" in CED_VIRAL_KNOWLEDGE_2026.lower()


def test_load_user_context_empty_without_db(monkeypatch):
    monkeypatch.setattr(
        "app.services.conversation_memory._get_recent_summaries",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "app.services.conversation_memory._get_top_memories",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "app.services.conversation_memory._get_pending_actions",
        lambda *_a, **_k: [],
    )
    assert load_user_context("00000000-0000-0000-0000-000000000001") == ""


def test_format_recall_empty():
    spoken = format_recall_for_voice({"ok": True, "results": []})
    assert "no encontré" in spoken.lower()


def test_recall_error_shape():
    data = {"ok": False, "error": "Memoria no disponible.", "results": []}
    spoken = format_recall_for_voice(data)
    assert "memoria" in spoken.lower()


def test_image_intent_still_works():
    assert is_generate_image_intent("crea una imagen de un ave")
