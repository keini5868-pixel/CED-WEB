"""Tests — prompt Seth activo y rutas conversacionales sin texto fijo."""

from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.services.voice_llm_common import needs_empathy_reformulation as _needs_empathy_reformulation
from app.services.retell_custom_llm import is_casual_conversation, is_generic_agent_line


def test_voice_prompt_includes_seth_v41_openai_strict_execution():
    prompt = build_ced_voice_system_prompt()
    assert "Seth" in prompt
    assert "CED — EXPERTISE" in prompt
    assert "Castillo Evolución Digital" in prompt
    assert "FUNCTION CALLING OBLIGATORIO" in prompt
    assert "NUNCA inventes comentarios" in prompt
    assert "SOLO BAJO COMANDO EXPLÍCITO" in prompt
    assert "Investigando, señor." in prompt
    assert "fallback=True" in prompt
    diag = voice_prompt_diagnostics()
    assert diag["includes_seth"] is True
    assert diag["includes_strict_tool_execution"] is True
    assert diag["prompt_version"] == "v41"
    assert diag["llm_provider"] == "openai_gpt41_mini"
    assert diag["prompt_chars"] > 4000


def test_casual_conversation_detects_tired_day():
    text = "Seth, hoy fue un día bastante agotador y me siento cansado"
    assert is_casual_conversation(text)


def test_generic_agent_line_detects_transactional():
    assert is_generic_agent_line("Muy bien, señor. ¿En qué puedo ayudarle?")


def test_needs_empathy_reformulation_for_generic():
    assert _needs_empathy_reformulation(
        "¿En qué puedo ayudarle, señor?",
        user_text="estoy cansado",
    )
