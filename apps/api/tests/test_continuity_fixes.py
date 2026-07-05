"""Tests — fixes de continuidad cámara y módulos."""

from __future__ import annotations

from app.services.ced_orchestrator import detect_module, is_module_command, is_topic_change
from app.services.cognitive_intents import (
    is_brand_followup_question,
    is_camera_deactivation_intent,
)
from app.services.retell_llm_types import Utterance


def test_camera_deactivation_intent():
    assert is_camera_deactivation_intent("apaga la cámara")
    assert is_camera_deactivation_intent("desactiva la camara")
    assert is_camera_deactivation_intent("cámara off")


def test_brand_followup_intent():
    assert is_brand_followup_question("¿de qué marca es?")
    assert is_brand_followup_question("dime la marca")


def test_topic_change_after_camera():
    assert is_topic_change("dime las noticias de hoy")
    assert is_topic_change("¿qué clima hay en Charlotte?")
    assert not is_topic_change("¿de qué marca es?")


def test_module_command_stays_camera_for_brand():
    transcript = [
        Utterance(role="agent", content="Es un suplemento, señor."),
        Utterance(role="user", content="¿de qué marca es?"),
    ]
    assert is_module_command(
        "¿de qué marca es?",
        "camera",
        transcript,
    )
    assert detect_module(
        "¿de qué marca es?",
        transcript,
        active_module="camera",
    ) == "camera"


def test_topic_change_clears_camera_for_news():
    transcript = [
        Utterance(role="user", content="¿qué me dices de las noticias del día?"),
    ]
    assert is_topic_change("¿qué me dices de las noticias del día?")
    assert not is_module_command(
        "¿qué me dices de las noticias del día?",
        "camera",
        transcript,
    )


def test_topic_change_detects_cambiando_el_tema_mid_sentence():
    assert is_topic_change("sabes hoy estoy con un dolor de cabeza cambiando el tema")
    assert is_topic_change("hablemos de otra cosa")
