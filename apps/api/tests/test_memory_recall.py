"""Tests — recall natural de conversaciones previas (chat y voz)."""

from app.services.cognitive_intents import is_conversation_recall_intent
from app.services.session_memory import (
    build_conversation_recall_reply,
    humanize_session_summary_for_user,
)


def test_is_conversation_recall_intent():
    assert is_conversation_recall_intent("hola me recuerdas nuestra conversacion anterior porfa")
    assert is_conversation_recall_intent("¿de qué hablamos la última vez?")
    assert not is_conversation_recall_intent("hola")


def test_humanize_session_summary_from_third_person():
    summary = (
        "El usuario solicitó un plan semanal de estrategia detallado para el lanzamiento de CED "
        "en formato PDF, el cual fue generado y entregado. Posteriormente, el usuario mencionó "
        "tener un dolor de cabeza, cambiando el tema."
    )
    topics = ["lanzamiento CED", "plan semanal"]
    text = humanize_session_summary_for_user(summary, topics)
    assert "hablamos de" in text.lower()
    assert "plan semanal" in text.lower()
    assert "pdf" in text.lower()
    assert "dolor de cabeza" in text.lower()
    assert "el usuario" not in text.lower()


def test_build_conversation_recall_reply_from_session_memory(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_memory.get_last_session_memory",
        lambda *_a, **_k: {
            "summary": (
                "El usuario solicitó un plan semanal de estrategia para el lanzamiento de CED en PDF."
            ),
            "topics": ["lanzamiento CED", "plan semanal"],
            "created_at": "2026-07-05T22:00:00+00:00",
        },
    )
    reply = build_conversation_recall_reply(
        "user-1",
        "me recuerdas nuestra conversacion anterior",
        channel="text",
    )
    assert reply.startswith("Claro.")
    assert "plan semanal" in reply.lower()
    assert "tool_code" not in reply.lower()
    assert "print(" not in reply.lower()


def test_build_conversation_recall_reply_voice_tone(monkeypatch):
    monkeypatch.setattr(
        "app.services.session_memory.get_last_session_memory",
        lambda *_a, **_k: {
            "summary": "Hablamos de prospección en Instagram.",
            "topics": ["Instagram", "prospección"],
            "created_at": "2026-07-04T10:00:00+00:00",
        },
    )
    reply = build_conversation_recall_reply(
        "user-1",
        "qué recuerdas de antes",
        channel="voice",
    )
    assert reply.startswith("Sí, señor.")


def test_hallucinated_recall_memory_resolves_to_natural_reply():
    from app.services.text_chat import _resolve_hallucinated_tool_code_reply

    reply = (
        'Claro, un momento.\n\n**tool_code**\n'
        'print(recall_memory(key="conversacion_anterior"))'
    )
    fixed = _resolve_hallucinated_tool_code_reply(
        reply,
        [{"role": "user", "content": "me recuerdas nuestra conversacion anterior"}],
        user_id="user-1",
        user_text="me recuerdas nuestra conversacion anterior",
    )
    assert fixed
    assert "tool_code" not in fixed.lower()
    assert "print(" not in fixed.lower()
