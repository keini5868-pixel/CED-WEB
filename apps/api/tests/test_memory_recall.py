"""Tests — recall natural de conversaciones previas (chat y voz)."""

from app.services.cognitive_intents import (
    CognitiveIntent,
    analyze_intent,
    is_conversation_recall_intent,
    parse_memory_save,
)
from app.services.session_memory import (
    build_conversation_recall_reply,
    humanize_session_summary_for_user,
)


def test_is_conversation_recall_intent():
    assert is_conversation_recall_intent("hola me recuerdas nuestra conversacion anterior porfa")
    assert is_conversation_recall_intent("¿de qué hablamos la última vez?")
    assert is_conversation_recall_intent("de que hablamos ayer")
    assert not is_conversation_recall_intent("hola")


def test_pasted_script_is_not_memory_save():
    script = (
        "Cinco hooks para elegir\n"
        "1. ¿Cansada de maquillarte las cejas diariamente?\n"
        "Hook recomendado: “¿Quieres cejas maquilladas sin maquillarte?”\n"
        "2. Guion educativo: Powder Shadow Brows\n"
        "ESCENA 4 - CONSEJO PRÁCTICO | 27-34 segundos\n"
        "Narración: “Recuerda que el resultado se suaviza durante la cicatrización "
        "y que, aproximadamente a los 40 días, realizamos un retoque.”\n"
    )
    assert parse_memory_save(script) is None
    assert analyze_intent(script).primary != CognitiveIntent.MEMORY_SAVE


def test_explicit_remember_this_still_saves():
    assert parse_memory_save("recuerda que mi nicho es micropigmentación de cejas")
    assert analyze_intent("recuerda que mi nicho es micropigmentación de cejas").primary == (
        CognitiveIntent.MEMORY_SAVE
    )


def test_cta_tweak_is_not_session_recall():
    """«eso de que hablamos por WhatsApp» es el CTA, no un pedido de memoria."""
    msg = (
        "Eso de que hablamos por whasatpp no me gusta es mejor algo como "
        "te gustaría saber cómo te quedarían un diseño personalizado"
    )
    assert is_conversation_recall_intent(msg) is False
    from app.services.cognitive_intents import CognitiveIntent, analyze_intent

    assert analyze_intent(msg).primary != CognitiveIntent.MEMORY_RECALL
    assert is_conversation_recall_intent("oye estamos creando un guion") is False


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
