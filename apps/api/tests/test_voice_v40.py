"""Tests — CED v40 prompt, saludos, anti-advanced auto, knowledge routing."""

from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.services.cognitive_intents import is_explicit_advanced_activation
from app.services.knowledge_router import route_knowledge
from app.services.retell_custom_llm import should_execute_advanced_now
from app.services.voice_greetings import JARVIS_GREETING_POOL, pick_jarvis_greeting


def test_voice_prompt_v43():
    prompt = build_ced_voice_system_prompt()
    assert "CED v43" in prompt
    assert "CED — EXPERTISE, EMPATÍA Y CERO FRICCIÓN" in prompt
    assert "sin limitaciones artificiales" in prompt
    assert "NO repitas ese filler" in prompt
    assert "SOLO BAJO COMANDO EXPLÍCITO" in prompt
    assert "Activa el modo avanzado" in prompt
    assert "REGLA 6 — TRANSPARENCIA DE USO" in prompt
    assert "NUNCA cortes a mitad de frase" in prompt
    assert "consultar_claude DE INMEDIATO" not in prompt
    assert "NUNCA busques web para opiniones" not in prompt
    diag = voice_prompt_diagnostics()
    assert diag["prompt_version"] == "v43"
    assert diag["llm_provider"] == "openai_gpt41_mini"
    assert diag["includes_advanced_explicit_only"] is True


def test_modo_avanzado_activation():
    cmd = "activa el modo avanzado para hacer una investigación"
    assert is_explicit_advanced_activation(cmd)
    assert should_execute_advanced_now(cmd, cmd)


def test_greeting_pool_has_eight():
    assert len(JARVIS_GREETING_POOL) == 8
    g = pick_jarvis_greeting(None)
    assert g
    assert "señor" in g.lower()


def test_advanced_not_auto_for_script():
    script = "Dame un guion de video para promocionar mi barbería"
    assert not should_execute_advanced_now(script, script)
    assert not is_explicit_advanced_activation(script)


def test_advanced_only_explicit_command():
    cmd = "Activa el sistema avanzado para investigar competencia"
    assert is_explicit_advanced_activation(cmd)
    assert should_execute_advanced_now(cmd, cmd)


def test_knowledge_route_level2_for_opinion():
    route = route_knowledge("Dame tu opinión sobre este guion de ventas")
    assert route.level in ("LEVEL-1", "LEVEL-2")
