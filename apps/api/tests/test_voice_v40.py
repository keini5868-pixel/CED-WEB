"""Tests — CED v43 prompt, saludos, knowledge routing (Gemini voz)."""

from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.services.knowledge_router import route_knowledge
from app.services.voice_greetings import JARVIS_GREETING_POOL, pick_jarvis_greeting


def test_voice_prompt_v43():
    prompt = build_ced_voice_system_prompt()
    assert "CED v43" in prompt
    assert "CED — EXPERTISE, EMPATÍA Y CERO FRICCIÓN" in prompt
    assert "sin limitaciones artificiales" in prompt
    assert "NO repitas ese filler" in prompt
    assert "DE INMEDIATO" not in prompt
    assert "SOLO BAJO COMANDO EXPLÍCITO" not in prompt
    assert "REGLA 6 — TRANSPARENCIA DE USO" in prompt
    assert "NUNCA cortes a mitad de frase" in prompt
    assert "NUNCA busques web para opiniones" not in prompt
    diag = voice_prompt_diagnostics()
    assert diag["prompt_version"] == "v43"
    assert diag["llm_provider"] == "gemini_2.5_flash"
    assert diag["includes_advanced_explicit_only"] is False


def test_greeting_pool_is_short():
    assert 3 <= len(JARVIS_GREETING_POOL) <= 8
    for g in JARVIS_GREETING_POOL:
        assert len(g) < 100
        assert "protocolos" not in g.lower()
        assert "misión" not in g.lower()
    g = pick_jarvis_greeting(None)
    assert g
    assert "ayudar" in g.lower() or "señor" in g.lower()


def test_knowledge_route_level2_for_opinion():
    route = route_knowledge("Dame tu opinión sobre este guion de ventas")
    assert route.level in ("LEVEL-1", "LEVEL-2")
