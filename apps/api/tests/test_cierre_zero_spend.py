"""CED Cierre: Realtime mini + conocimiento interno + sin tools caras."""

from app.domain.openai_voice_prompt import build_realtime_instructions
from app.services.openai_realtime import (
    DEFAULT_FITLINE_REALTIME_MODEL,
    _models_to_try,
)
from app.services.openai_voice_tools import (
    FITLINE_CIERRE_TOOL_NAMES,
    fitline_cierre_realtime_tools,
)
from app.services.opportunities_pilot.fitline_knowledge import (
    format_fitline_knowledge_lean_for_voice,
)


def test_fitline_models_are_mini_only():
    models = _models_to_try(DEFAULT_FITLINE_REALTIME_MODEL, mini_only=True)
    assert models
    assert all("mini" in m.lower() for m in models)
    assert "gpt-realtime" not in models  # full model excluded
    assert models[0] == DEFAULT_FITLINE_REALTIME_MODEL


def test_fitline_cierre_tools_only_franchise():
    tools = fitline_cierre_realtime_tools()
    names = {str(t.get("name") or "") for t in tools}
    assert names == set(FITLINE_CIERRE_TOOL_NAMES)
    assert "search_web" not in names
    assert "generate_image" not in names
    assert "play_youtube_video" not in names


def test_lean_knowledge_bans_external_spend():
    text = format_fitline_knowledge_lean_for_voice(max_chars=7_500)
    assert "CONOCIMIENTO INTERNO" in text or "HECHOS" in text
    assert "PROHIBIDO" in text or "COSTO CERO" in text
    assert len(text) <= 7_600


def test_realtime_fitline_instructions_zero_spend(monkeypatch):
    monkeypatch.setattr(
        "app.services.opportunities_pilot.fitline_guide_mode.is_fitline_admin_user",
        lambda _uid: True,
    )
    prompt = build_realtime_instructions(
        language="es",
        voice_pace=50,
        voice_warmth=55,
        voice_energy=50,
        response_speed="balanced",
        voice_profile="fitline",
        user_id="admin-user",
    )
    low = prompt.lower()
    assert "paridad retell" in low or "motor de voz cierre" in low
    assert "restorate" in low or "ntc" in low
    assert "más información" in low
    assert "jarvis" in low
    assert "search_web" in low or "tavily" in low or "prohibido" in low
