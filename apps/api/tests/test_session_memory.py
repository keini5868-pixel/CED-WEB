"""Tests — memoria sesión a sesión."""

from app.services.session_memory import (
    build_memory_greeting,
    build_text_chat_welcome,
    calculate_days_ago,
    fallback_summary_from_history,
    format_history,
    get_session_memory_context,
    looks_like_raw_transcript,
    sanitize_public_summary,
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


def test_looks_like_raw_transcript():
    assert looks_like_raw_transcript("user: hola\nassistant: Hola señor")
    assert not looks_like_raw_transcript("Hablamos de estrategia semanal para CED.")


def test_sanitize_public_summary_strips_transcript():
    raw = "user: hola\nassistant: Hola, señor. ¿En qué puedo asistirle?"
    cleaned = sanitize_public_summary(raw)
    assert "user:" not in cleaned.lower()
    assert "assistant:" not in cleaned.lower()
    assert "hola" in cleaned.lower()


def test_fallback_summary_never_leaks_transcript_in_public():
    history = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "Hola, señor."},
        {"role": "user", "content": "estrategia de lanzamiento CED"},
    ]
    fb = fallback_summary_from_history(history)
    assert not looks_like_raw_transcript(str(fb.get("summary_short") or ""))
    assert "lanzamiento" in str(fb.get("internal_detail") or "").lower()


def test_calculate_days_ago_yesterday():
    label = calculate_days_ago("2026-07-03T12:00:00+00:00")
    assert label.startswith("hace") or label == "ayer"


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
            "summary": "Trabajamos la estrategia de lanzamiento de CED.",
            "topics": ["lanzamiento CED", "marketing"],
            "tasks_executed": ["plan semanal"],
            "created_at": "2026-07-03T10:00:00+00:00",
        },
    )
    greeting = build_memory_greeting("user-1")
    assert greeting
    assert "Bienvenido de nuevo" in greeting
    assert "lanzamiento" in greeting.lower()
    assert "user:" not in greeting.lower()


def test_build_memory_greeting_sanitizes_bad_summary(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_memory.get_last_session_memory",
        lambda *_a, **_k: {
            "summary": "user: hola\nassistant: Hola señor",
            "topics": [],
            "tasks_executed": [],
            "created_at": "2026-07-03T10:00:00+00:00",
        },
    )
    greeting = build_memory_greeting("user-1")
    assert greeting
    assert "user:" not in greeting.lower()
    assert "assistant:" not in greeting.lower()


def test_get_session_memory_context(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_memory.get_last_session_memory",
        lambda *_a, **_k: {
            "summary": "Hablamos de estrategia en redes.",
            "internal_context": "Detalle: plan de lanzamiento CED, público emprendedores, calendario semanal acordado.",
            "topics": ["redes sociales", "lanzamiento CED"],
            "tasks_executed": ["buscó noticias"],
            "projects": ["CED"],
            "user_context": {"publico": "emprendedores"},
            "created_at": "2026-07-01T10:00:00+00:00",
        },
    )
    ctx = get_session_memory_context("user-1")
    assert "MEMORIA DE SESIÓN ANTERIOR" in ctx
    assert "NO LEER AL USUARIO" in ctx
    assert "lanzamiento CED" in ctx
    assert "PROHIBIDO decir que no retienes historial" in ctx


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
            "summary_short": "Publicación en Instagram.",
            "internal_detail": "El usuario pidió publicar en Instagram y CED confirmó la acción.",
            "topics": ["Instagram"],
            "tasks": ["publicó en Instagram"],
            "projects": [],
            "user_context": {},
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
    assert "Instagram" in stored["internal_context"]
    assert stored["topics"] == ["Instagram"]
    assert stored["tasks_executed"] == ["publicó en Instagram"]
