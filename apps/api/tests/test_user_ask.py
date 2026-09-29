from __future__ import annotations

from app.services.cognitive_intents import CognitiveIntent, analyze_intent
from app.services.module_detector import detect_intent
from app.services.user_ask import extract_user_ask, is_llm_first_turn, module_probe_text
from app.services.voice_intent_gate import has_explicit_module_signal, should_run_orchestrator


HOOKS_PASTE = (
    "# 5 Hooks alternativos para probar\n"
    "¿Y si pudieras tener un negocio generando ingresos sin inventar nada?\n"
    "Descubrí cómo personas generan ingresos reales en 90 días.\n"
    "## Guion completo\n"
    "[HOOK — 0–4 s] ¿Y si pudieras\n"
    "Te explico el proyecto — qué es, cómo funciona. Hoy te muestro la alternativa.\n"
    "Elige el hook que más resuene. dime en una sola frase que te parecen estas opciones"
)


def test_extract_ask_from_long_hooks_paste() -> None:
    ask = extract_user_ask(HOOKS_PASTE)
    assert "te parecen" in ask.lower()
    assert is_llm_first_turn(HOOKS_PASTE) is True
    assert "te parecen" in module_probe_text(HOOKS_PASTE).lower()


def test_hooks_opinion_does_not_run_finance_or_voice_modules() -> None:
    assert analyze_intent(HOOKS_PASTE).primary == CognitiveIntent.INTERNAL_KNOWLEDGE
    assert detect_intent(HOOKS_PASTE, run_stage2=False).activate is False
    assert has_explicit_module_signal(HOOKS_PASTE) is False
    assert should_run_orchestrator(HOOKS_PASTE) is False


def test_short_finance_question_still_routes() -> None:
    assert is_llm_first_turn("cómo voy este mes con mis finanzas") is False
    assert has_explicit_module_signal("consulta mis finanzas") is True
    assert has_explicit_module_signal("Guárdame en finanzas que gasté 50 dólares") is True


def test_opinion_on_hooks_is_not_a_module() -> None:
    text = "qué te parecen estos hooks para generar ingresos"
    assert is_llm_first_turn(text) is True
    assert has_explicit_module_signal(text) is False
