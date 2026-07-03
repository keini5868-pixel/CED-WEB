"""Auditoría voz — escenarios críticos sin pegarse ni silencio."""

from __future__ import annotations

from app.services.cognitive_intents import is_personal_vent_intent, is_weather_intent
from app.services.gemini_voice_tools import build_gemini_voice_tools
from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS
from app.services.retell_custom_llm import resolve_web_search_request
from app.services.retell_llm_types import Utterance
from app.services.voice_llm_common import ensure_voice_reply, FALLBACK_REPLY
from app.services.voice_spoken import finalize_voice_delivery_text


def _tx(text: str) -> list[Utterance]:
    return [Utterance(role="user", content=text)]


def test_scenario_basic_greeting_not_web():
    text = "Hola, ¿cómo estás?"
    assert resolve_web_search_request(text, _tx(text)) is None


def test_scenario_trump_news_triggers_web():
    text = "Dame las últimas noticias de Donald Trump"
    req = resolve_web_search_request(text, _tx(text))
    assert req is not None
    assert req["kind"] == "news"


def test_scenario_weather_charlotte():
    text = "¿Qué clima hay hoy en Charlotte?"
    assert is_weather_intent(text)
    req = resolve_web_search_request(text, _tx(text))
    assert req is not None
    assert req["kind"] == "weather"


def test_scenario_personal_vent_not_weather():
    text = (
        "Me siento mal porque cada mes no alcanza para la renta y mi esposa "
        "tiene que ayudarme. Ya tengo tanto tiempo en esta situación."
    )
    assert is_personal_vent_intent(text)
    assert not is_weather_intent(text)
    assert resolve_web_search_request(text, _tx(text)) is None


def test_scenario_advice_question_is_personal():
    text = "¿Cuál sería el consejo que tú me puedes dar en esta situación?"
    assert is_personal_vent_intent(text)


def test_all_realtime_tools_exposed_to_gemini():
    openai_names = {str(t.get("name")) for t in OPENAI_REALTIME_TOOLS if t.get("name")}
    gemini_names = {
        decl.name
        for decl in (build_gemini_voice_tools().function_declarations or [])
        if decl.name
    }
    required = {
        "search_web",
        "generar_pdf",
        "generate_image",
        "analyze_camera_frame",
        "publicar_facebook",
        "publicar_instagram",
    }
    assert required.issubset(openai_names)
    assert required.issubset(gemini_names)


def test_ensure_voice_reply_never_empty():
    assert ensure_voice_reply("") == FALLBACK_REPLY
    assert ensure_voice_reply("Hola señor.") == "Hola señor."


def test_finalize_strips_markdown_for_voice():
    out = finalize_voice_delivery_text("Mi consejo es **no culparte**, señor.")
    assert "**" not in out
    assert "no culparte" in out
