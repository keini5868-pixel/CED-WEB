"""Retomar trabajo de otra conversación: el historial del modelo es por hilo."""

from __future__ import annotations

from app.services.chat_continuity import (
    append_previous_thread_if_needed,
    previous_thread_block,
    wants_previous_thread,
)

UID = "24b62e5d-052b-407e-a9ee-3d2f416f07a1"
PREV = "conv-anterior"
CURRENT = "conv-actual"


def _fake_db(monkeypatch, messages: list[dict[str, str]]) -> None:
    monkeypatch.setattr(
        "app.services.supabase_db.list_conversations",
        lambda uid, limit=6, **_k: [
            {"id": CURRENT, "title": "Conversación CED"},
            {"id": PREV, "title": "Mini serie de Instagram"},
        ],
    )
    monkeypatch.setattr(
        "app.services.supabase_db.get_conversation_messages",
        lambda cid, uid, limit=40: messages if cid == PREV else [],
    )


def test_detects_retomar_and_similar_phrases():
    assert wants_previous_thread("vamos a retomar el guion") is True
    assert wants_previous_thread("sigamos con lo que hablamos ayer") is True
    assert wants_previous_thread("quiero un cierre más suave para ese guion") is True
    assert wants_previous_thread("la conversación anterior quedó a medias") is True


def test_ignores_fresh_requests():
    assert wants_previous_thread("hola") is False
    assert wants_previous_thread("dame ideas de reel sobre IA") is False
    assert wants_previous_thread("") is False


def test_block_brings_previous_thread_tail(monkeypatch):
    _fake_db(
        monkeypatch,
        [
            {"role": "user", "content": "dame un guion para la mini serie"},
            {"role": "model", "content": "Gancho: nadie te dijo esto..."},
        ],
    )
    block = previous_thread_block(UID, CURRENT)
    assert "Mini serie de Instagram" in block
    assert "Gancho: nadie te dijo esto..." in block
    assert "Usuario: dame un guion para la mini serie" in block


def test_block_skips_the_current_thread(monkeypatch):
    _fake_db(monkeypatch, [])
    assert previous_thread_block(UID, CURRENT) == ""


def test_prepends_only_on_fresh_thread(monkeypatch):
    _fake_db(
        monkeypatch,
        [{"role": "model", "content": "Gancho: nadie te dijo esto..."}],
    )
    text = "vamos a retomar el guion, quiero un cierre más suave"

    fresh = append_previous_thread_if_needed("SYSTEM", UID, text, CURRENT, [])
    assert fresh.startswith("# CONTINUIDAD")
    assert fresh.endswith("SYSTEM")

    ongoing = append_previous_thread_if_needed(
        "SYSTEM",
        UID,
        text,
        CURRENT,
        [{"role": "user", "content": str(i)} for i in range(9)],
    )
    assert ongoing == "SYSTEM"


def test_untouched_when_intent_absent(monkeypatch):
    _fake_db(monkeypatch, [{"role": "model", "content": "algo"}])
    assert (
        append_previous_thread_if_needed("SYSTEM", UID, "dame 3 ideas de reel", CURRENT, [])
        == "SYSTEM"
    )
