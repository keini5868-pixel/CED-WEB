"""Tests — memoria sesión a sesión."""

from app.services.session_memory import (
    build_memory_greeting,
    build_text_chat_welcome,
    calculate_days_ago,
    format_history,
    get_session_memory_context,
    save_session_memory,
)


def test_format_history():
    history = [
        {"role": "user", "content": "Hola CED"},
        {"role": "assistant", "content": "A sus órdenes, señor."},
    ]
    text = format_history(history)
    assert "user: Hola CED" in text
    assert "assistant: A sus órdenes" in text


def test_calculate_days_ago_yesterday():
    assert calculate_days_ago("2026-07-03T12:00:00+00:00") in {
        "ayer",
        "hace 1 días",
        "hace un momento",
        "hace 0 horas",
    }


def test_build_memory_greeting_without_db(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_memory.get_last_session_memory",
        lambda *_a, **_k: None,
    )
    assert build_memory_greeting("user-1") is None
    assert "Hola, soy CED" in build_text_chat_welcome("user-1")


def test_build_memory_greeting_with_memory(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_memory.get_last_session_memory",
        lambda *_a, **_k: {
            "summary": "Publicamos un creativo FitLine en Instagram.",
            "topics": ["FitLine", "publicaciones"],
            "tasks_executed": ["publicó en Instagram"],
            "created_at": "2026-07-03T10:00:00+00:00",
        },
    )
    greeting = build_memory_greeting("user-1")
    assert greeting
    assert "Bienvenido de nuevo" in greeting
    assert "FitLine" in greeting
    assert "Continuamos" in greeting


def test_get_session_memory_context(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_memory.get_last_session_memory",
        lambda *_a, **_k: {
            "summary": "Hablamos de estrategia en redes.",
            "topics": ["redes sociales"],
            "tasks_executed": ["buscó noticias"],
            "created_at": "2026-07-01T10:00:00+00:00",
        },
    )
    ctx = get_session_memory_context("user-1")
    assert "MEMORIA DE SESIÓN ANTERIOR" in ctx
    assert "estrategia" in ctx
    assert "buscó noticias" in ctx


def test_save_session_memory_skips_short_session(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr(
        "app.services.session_memory.get_conversation_history",
        lambda *_a, **_k: [{"role": "user", "content": "hola"}],
    )

    class _T:
        def upsert(self, *_a, **_k):
            calls.append({"upsert": True})
            return self

        def execute(self):
            return self

    class _Client:
        def table(self, _name):
            return _T()

    monkeypatch.setattr("app.services.session_memory._client", lambda: _Client())
    save_session_memory(user_id="u1", session_id="s1")
    assert calls == []


def test_save_session_memory_persists(monkeypatch):
    stored: dict = {}

    monkeypatch.setattr(
        "app.services.session_memory.get_conversation_history",
        lambda *_a, **_k: [
            {"role": "user", "content": "publica en instagram"},
            {"role": "assistant", "content": "Listo, señor."},
        ],
    )
    monkeypatch.setattr(
        "app.services.session_memory.gemini_summarize_session",
        lambda *_a, **_k: {
            "text": "Publicación en Instagram.",
            "topics": ["Instagram"],
            "tasks": ["publicó en Instagram"],
        },
    )

    class _Query:
        def upsert(self, row, on_conflict=None):
            stored.update(row)
            return self

        def execute(self):
            return self

    class _Client:
        def table(self, _name):
            return _Query()

    monkeypatch.setattr("app.services.session_memory._client", lambda: _Client())

    save_session_memory(user_id="u1", session_id="call-123")
    assert stored["user_id"] == "u1"
    assert stored["session_id"] == "call-123"
    assert stored["summary"] == "Publicación en Instagram."
    assert stored["topics"] == ["Instagram"]
    assert stored["tasks_executed"] == ["publicó en Instagram"]
