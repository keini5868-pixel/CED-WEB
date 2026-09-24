"""Tests — coalescing de parciales de streaming en append_message."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.supabase_db import _should_coalesce_voice_model_message, append_message


def test_coalesce_extends_previous_model_message():
    assert _should_coalesce_voice_model_message(
        "Claro, señor.",
        "Claro, señor. Con gusto le contaré a Oliver",
    ) == "update"


def test_coalesce_skips_shorter_partial():
    assert _should_coalesce_voice_model_message(
        "Claro, señor. Con gusto",
        "Claro, señor.",
    ) == "skip"


def test_coalesce_no_match_for_unrelated():
    assert _should_coalesce_voice_model_message(
        "Soy CED.",
        "Soy CED.",
    ) == "skip"


def test_coalesce_skips_exact_duplicate():
    assert _should_coalesce_voice_model_message(
        "Soy CED.",
        "Soy CED.",
    ) == "skip"


class _FakeTable:
    def __init__(self, name: str, last_message: dict, inserts: list[dict]):
        self.name = name
        self.last_message = last_message
        self.inserts = inserts
        self.op = "select"

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def insert(self, payload):
        self.inserts.append(payload)
        self.op = "insert"
        return self

    def update(self, _payload):
        self.op = "update"
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        if self.op != "select":
            return SimpleNamespace(data=[])
        if self.name == "voice_conversations":
            return SimpleNamespace(data=[{"id": "conv-1", "channel": "text"}])
        return SimpleNamespace(data=[self.last_message])


def test_append_skips_greeting_already_last_in_thread(monkeypatch):
    """Cada activación de voz reescribía el saludo y el hilo lo acumulaba."""
    greeting = "Hola de nuevo. ¿En qué lo puedo ayudar?"
    inserts: list[dict] = []
    last = {
        "id": "m-old",
        "role": "model",
        "content": greeting,
        "created_at": "2020-01-01T00:00:00+00:00",  # fuera de la ventana de coalescing
    }
    monkeypatch.setattr(
        "app.services.supabase_db._client",
        lambda: SimpleNamespace(table=lambda name: _FakeTable(name, last, inserts)),
    )

    append_message("conv-1", "user-1", "model", greeting)
    assert inserts == []

    append_message("conv-1", "user-1", "model", "Son las diez, señor.")
    assert len(inserts) == 1
