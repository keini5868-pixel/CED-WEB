"""Tests — calidad de respuesta en chat (dedupe, web vs KB, publish off-topic)."""

from __future__ import annotations

from unittest.mock import patch

from app.services.cognitive_intents import CognitiveIntent, analyze_intent
from app.services.cognitive_router import route_message
from app.services.publish_text import extract_caption_from_turn
from app.services.text_chat import (
    _dedupe_chat_reply,
    _ensure_chat_reply_quality,
    _finalize_chat_reply,
    _is_deliverable_request,
    _is_incomplete_deliverable,
)
from app.services.text_publish_flow import _publish_turn_is_off_topic


def test_analyze_intent_research_before_internal():
    analysis = analyze_intent(
        "¿Han investigado otras personas la teoría de que los terremotos vienen de energía humana?"
    )
    assert analysis.primary == CognitiveIntent.WEB_SEARCH


def test_route_message_prefers_web_over_internal_kb():
    with patch("app.services.cognitive_router.execute_search_web_sync") as mock_search:
        mock_search.return_value = {
            "ok": True,
            "summary": "Estudios recientes sobre correlaciones sísmicas.",
            "source": "tavily",
        }
        result = route_message(
            "user-test",
            "¿Existen estudios sobre terremotos y energía humana?",
            channel="text",
            execute_side_effects=False,
        )
    assert result.intent == CognitiveIntent.WEB_SEARCH.value
    assert "Estudios" in (result.speakable or "")
    mock_search.assert_called_once()


def test_finalize_chat_reply_strips_duplicate_filler():
    raw = "Un momento, señor.Un momento, señor. Según fuentes recientes, Trump declaró..."
    out = _finalize_chat_reply(raw)
    assert out.count("Un momento") <= 1
    assert "Trump" in out


def test_dedupe_chat_reply_removes_repeated_blocks():
    dup = "Primer párrafo.\n\nPrimer párrafo.\n\nSegundo párrafo."
    assert _dedupe_chat_reply(dup) == "Primer párrafo.\n\nSegundo párrafo."


def test_ensure_chat_reply_quality_replaces_kb_leak():
    kb_reply = (
        "Keini Castillo es el creador de CED. Su propósito es ayudar a las personas "
        "a desarrollar hábitos de repetición en contexto estable."
    )
    with patch(
        "app.services.text_chat._reply_from_direct_search",
        return_value="Investigaciones recientes no confirman esa teoría.",
    ):
        out = _ensure_chat_reply_quality(
            kb_reply,
            user_text="¿Han investigado terremotos y energía humana?",
        )
    assert "Keini Castillo" not in out
    assert "Investigaciones" in out


def test_publish_flow_off_topic_clears_long_research():
    monologue = (
        "He estado pensando en la teoría de que los terremotos podrían estar relacionados "
        "con la energía acumulada de millones de personas en estados emocionales intensos. "
        "¿Existen estudios científicos serios sobre esto en internet?"
    )
    assert _publish_turn_is_off_topic(monologue) is True
    assert _publish_turn_is_off_topic("publica en facebook") is False


def test_long_monologue_not_plain_caption():
    long_text = " ".join(["palabra"] * 80)
    assert extract_caption_from_turn(long_text) == ""


def test_is_deliverable_request_detects_strategy():
    assert _is_deliverable_request(
        "ok perfecto crea una estrategia semanal para estas soluciones"
    )


def test_is_incomplete_deliverable_intro_only():
    user = "crea una estrategia semanal y a que publico dirigirla"
    reply = (
        "Entendido, señor. Aquí le presento una estrategia semanal enfocada "
        "en las soluciones más relevantes de CED, dirigida a un público"
    )
    assert _is_incomplete_deliverable(reply, user) is True


def test_is_complete_deliverable_with_weekly_structure():
    user = "crea una estrategia semanal"
    reply = (
        "## Público objetivo\nEmprendedores de marketing digital.\n\n"
        "## Semana\n"
        "**Lunes:** Prospección en Instagram.\n"
        "**Martes:** Publicar reel educativo.\n"
        "**Miércoles:** Análisis de métricas.\n"
        "**Jueves:** Generar creativos con CED.\n"
        "**Viernes:** Seguimiento de leads.\n"
    )
    assert _is_incomplete_deliverable(reply, user) is False


def test_finalize_chat_reply_preserves_markdown_newlines():
    raw = "## Plan\n\n**Lunes:** acción 1.\n\n**Martes:** acción 2."
    out = _finalize_chat_reply(raw)
    assert "\n" in out
    assert "**Lunes:**" in out or "Lunes" in out
