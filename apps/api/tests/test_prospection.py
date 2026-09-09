"""Modo prospección — comandos vs copy, y scoring de comentarios."""

from __future__ import annotations

from app.services.ced_orchestrator import detect_module_from_patterns
from app.services.module_detector import CONF_ANCHOR, CONF_NONE, detect_intent
from app.services.prospection import _score_comment, is_prospection_mode_command
from app.services.text_chat import CHAT_TOOLS, _needs_chat_tools
from app.services.voice_intent_gate import has_explicit_module_signal


def test_mode_command_phrases() -> None:
    assert is_prospection_mode_command("activa modo de prospección")
    assert is_prospection_mode_command("activa asistente de voz") is False
    assert is_prospection_mode_command("activa el modo de prospeccion")
    assert is_prospection_mode_command("dame el reporte de prospección")
    assert is_prospection_mode_command("ayúdame con un mensaje de prospección") is False
    assert is_prospection_mode_command("ideas de prospección para FitLine") is False


def test_chat_loads_tools_only_on_mode_command() -> None:
    names = {t["name"] for t in CHAT_TOOLS}
    assert "activar_prospeccion" in names
    assert "reporte_prospeccion" in names
    assert _needs_chat_tools("activa el modo de prospección") is True
    assert _needs_chat_tools("prepárame un mensaje de prospección") is False


def test_copy_about_prospection_does_not_hijack_ced() -> None:
    phrase = "prepárame un mensaje de prospección para FitLine"
    assert has_explicit_module_signal(phrase) is False
    d = detect_intent(phrase, classify=lambda *_: True)
    assert d.activate is False
    assert d.confidence == CONF_NONE
    assert detect_module_from_patterns(phrase) is None


def test_strict_modo_de_prospection() -> None:
    d = detect_intent("activa el modo de prospección", classify=lambda *_: False)
    assert d.module == "prospection"
    assert d.confidence == CONF_ANCHOR
    assert d.activate is True


def test_score_hot_comment() -> None:
    score, is_hot, intent = _score_comment("Hola, ¿cuál es el precio? Quiero comprar por WhatsApp")
    assert score >= 70
    assert is_hot is True
    assert "precio" in intent or "interés" in intent
