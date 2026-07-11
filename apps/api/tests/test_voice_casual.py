"""Tests — path rápido de charla casual en voz (KB interno + Llama, sin orquestador)."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.retell_custom_llm import is_casual_conversation, is_small_talk
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance
from app.services.voice_casual import is_casual_voice_turn, try_internal_knowledge_voice_reply
from app.services.voice_intent_gate import should_run_orchestrator


CASUAL_PHRASES: tuple[str, ...] = (
    "trabajé hasta las 4 de la madrugada y ahorita me acabo de despertar",
    "hoy fue un día bastante agotador y me siento cansado",
    "no dormí nada anoche, estoy hecho polvo",
    "qué lunes tan pesado, ni ganas de trabajar tengo",
    "acabo de desayunar y ya quiero volver a la cama",
    "me siento un poco triste hoy, no sé por qué",
    "gracias por escucharme, de verdad lo necesitaba",
    "estuve todo el día en reuniones y no aguanto más",
    "qué opinas del café con leche por las mañanas",
    "anoche vi una película muy mala y perdí el tiempo",
    "hola, ¿cómo estás?",
    "buenos días, señor",
    "la verdad hoy amanecí de mal humor",
    "me duele un poco la cabeza desde temprano",
    "qué fastidio el tráfico de la mañana",
)

MODULE_PHRASES: tuple[str, ...] = (
    "genera una imagen de un árbol",
    "publica esto en instagram",
    "activa la cámara",
    "¿qué clima hace hoy?",
    "busca noticias de tecnología",
)


def test_casual_phrases_classified_as_casual_voice_turn() -> None:
    for phrase in CASUAL_PHRASES:
        assert is_casual_voice_turn(phrase), phrase
        assert not should_run_orchestrator(phrase), phrase


def test_module_phrases_not_casual_voice_turn() -> None:
    for phrase in MODULE_PHRASES:
        assert not is_casual_voice_turn(phrase), phrase


def test_user_reported_phrase_no_longer_blocked_as_task_query() -> None:
    text = "trabajé hasta las 4 de la madrugada y ahorita me acabo de despertar"
    assert is_casual_conversation(text)
    assert is_casual_voice_turn(text)
    assert not is_small_talk(text)
    assert not should_run_orchestrator(text)


def test_casual_llama_system_is_minimal_without_tools() -> None:
    from app.services.voice_casual import build_casual_llama_system

    system = build_casual_llama_system("me siento cansado hoy")
    assert len(system) < 1800
    assert "FUNCTION CALLING" not in system
    assert "Gemini" not in system
    assert "search_web" not in system
    assert "señor" in system.lower() or "senor" in system.lower()


def test_internal_kb_concept_question_is_casual_voice_turn() -> None:
    text = "¿Qué es un embudo de ventas?"
    assert is_casual_voice_turn(text)
    assert not should_run_orchestrator(text)
    reply, source = try_internal_knowledge_voice_reply("¿Qué es un embudo de ventas?")
    if reply:
        assert source == "internal_kb"
        assert len(reply) > 10


@pytest.mark.parametrize("phrase", CASUAL_PHRASES)
def test_casual_draft_under_four_seconds(monkeypatch: pytest.MonkeyPatch, phrase: str) -> None:
    """Llama mockeado — el path casual debe resolver en <4s sin orquestador."""
    from app.services import llama_service as ls
    from app.services.llama_voice_llm import LlamaVoiceLlm

    def _fast_llama(**kwargs: object) -> str:  # noqa: ANN003
        return "Entiendo, señor. Descanse un poco cuando pueda."

    monkeypatch.setattr(ls, "llama_voice_model_ready", lambda **k: True)
    monkeypatch.setattr("app.services.llama_voice_llm.call_llama_voice_chat", _fast_llama)

    llm = LlamaVoiceLlm()
    llm.set_user_id("test-user")
    request = ResponseRequiredRequest(
        interaction_type="response_required",
        response_id=1,
        transcript=[Utterance(role="user", content=phrase)],
    )

    started = time.perf_counter()
    reply = asyncio.run(llm.draft_conversational_response(request))
    elapsed = time.perf_counter() - started

    assert reply
    assert elapsed < 4.0, f"{phrase!r} tardó {elapsed:.2f}s"


def test_casual_llama_uses_low_token_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import llama_service as ls
    from app.services.llama_voice_llm import LlamaVoiceLlm
    from app.services.voice_casual import LLAMA_CASUAL_MAX_TOKENS, LLAMA_CASUAL_TEMPERATURE

    captured: dict = {}

    def _capture(**kwargs: object) -> str:  # noqa: ANN003
        captured.update(kwargs)
        return "Comprendo, señor."

    monkeypatch.setattr(ls, "llama_voice_model_ready", lambda **k: True)
    monkeypatch.setattr("app.services.llama_voice_llm.call_llama_voice_chat", _capture)

    llm = LlamaVoiceLlm()
    phrase = "estoy cansado hoy"
    request = ResponseRequiredRequest(
        interaction_type="response_required",
        response_id=2,
        transcript=[Utterance(role="user", content=phrase)],
    )
    asyncio.run(llm.draft_conversational_response(request))

    assert captured.get("max_tokens") == LLAMA_CASUAL_MAX_TOKENS
    assert captured.get("temperature") == LLAMA_CASUAL_TEMPERATURE
    assert captured.get("timeout_sec") == 12.0
    assert captured.get("num_ctx") == 2048


def test_voice_safety_timeout_is_25_seconds() -> None:
    from app.services.llama_voice_llm import LLAMA_VOICE_TIMEOUT_SEC
    from app.services.voice_casual import LLAMA_VOICE_SAFETY_TIMEOUT_SEC

    assert LLAMA_VOICE_TIMEOUT_SEC == 25.0
    assert LLAMA_VOICE_SAFETY_TIMEOUT_SEC == 25.0
