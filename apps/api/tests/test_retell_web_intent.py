"""Tests — detección web Retell (sin mezclar noticias previas)."""

from app.services.retell_custom_llm import resolve_web_search_request
from app.services.retell_llm_types import Utterance


def _tx(*lines: tuple[str, str]) -> list[Utterance]:
    return [Utterance(role=role, content=text) for role, text in lines]


def test_trump_news_intent():
    text = "Sí, dime las últimas noticias de Donald Trump."
    tx = _tx(("agent", "CED en línea, señor."), ("user", text))
    req = resolve_web_search_request(text, tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "donald trump" in req["query"].lower()


def test_trump_news_after_ack_fragment():
    tx = _tx(
        ("agent", "CED en"),
        ("user", "Sí"),
        ("user", "dime las últimas noticias de Donald Trump"),
    )
    merged = tx[-1].content
    req = resolve_web_search_request(merged, tx)
    assert req is not None
    assert req["kind"] == "news"


def test_news_only_last_turn():
    tx = _tx(
        ("user", "Sí, dime las noticias del día de hoy en Estados Unidos."),
    )
    req = resolve_web_search_request(tx[-1].content, tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "noticias" in req["query"].lower()


def test_creatine_not_news_after_news_turn():
    tx = _tx(
        ("user", "Sí, dime las noticias del día de hoy en Estados Unidos."),
        ("user", "Búscame en la web qué es la creatina."),
    )
    last = tx[-1].content
    req = resolve_web_search_request(last, tx)
    assert req is not None
    assert req["kind"] == "general"
    assert "creatina" in req["query"].lower()
    assert "noticias" not in req["query"].lower()


def test_fragment_country_completes_news():
    tx = _tx(
        ("user", "Dime las últimas noticias"),
        ("user", "de Estados Unidos."),
    )
    last = tx[-1].content
    req = resolve_web_search_request(last, tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "Estados Unidos" in req["query"]


def test_ack_only_skipped():
    tx = _tx(("user", "Okay."),)
    assert resolve_web_search_request("Okay.", tx) is None


def test_creatine_definition_no_web_without_explicit_request():
    tx = _tx(("user", "Qué es la creatina?"))
    assert resolve_web_search_request(tx[-1].content, tx) is None


def test_creatine_internal_not_web():
    from app.services.cognitive_intents import is_internal_knowledge_query

    tx = _tx(("user", "Yo sé lo que es la creatina"))
    assert is_internal_knowledge_query(tx[-1].content)
    assert resolve_web_search_request(tx[-1].content, tx) is None


def test_world_news_triggers_web():
    tx = _tx(("user", "Dame las noticias más relevantes del mundo"))
    req = resolve_web_search_request(tx[-1].content, tx)
    assert req is not None
    assert req["kind"] == "news"


def test_venezuela_news_triggers_web():
    tx = _tx(("user", "Dame las últimas noticias de Venezuela"))
    req = resolve_web_search_request(tx[-1].content, tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "venezuela" in req["query"].lower()


def test_investigate_intent_triggers_web():
    tx = _tx(("user", "Investiga lo que pasó con el terremoto en Venezuela"))
    req = resolve_web_search_request(tx[-1].content, tx)
    assert req is not None


def test_casual_long_text_not_search():
    from app.services.retell_custom_llm import is_casual_conversation

    text = (
        "Hoy dormí muy mal y estuve pensando en muchas cosas del trabajo "
        "y de la familia durante toda la noche sin poder descansar bien"
    )
    assert is_casual_conversation(text) is True
    assert resolve_web_search_request(text, _tx(("user", text))) is None


def test_personal_vent_not_weather_or_web():
    from app.services.cognitive_intents import is_personal_vent_intent, is_weather_intent
    from app.services.retell_custom_llm import is_casual_conversation

    text = (
        "Yo creo que me dejó un consejo, porque me siento mal. Últimamente las cosas "
        "no se me dan. La semana pasada hice un trabajo, me lo tenían que pagar hoy "
        "y no me lo pagaron. Cada vez que tengo que pagar la renta todo se complica "
        "y quedo sin dinero. Mi esposa tiene que apoyarme y no quiero depender de nadie. "
        "Ya tengo tanto tiempo en esta situación mes tras mes que estoy cansado."
    )
    assert is_personal_vent_intent(text)
    assert not is_weather_intent(text)
    assert is_casual_conversation(text)
    assert resolve_web_search_request(text, _tx(("user", text))) is None


def test_figurative_tiempo_en_not_weather():
    from app.services.cognitive_intents import is_weather_intent

    assert not is_weather_intent("Ya tengo tanto tiempo en esta situación mes tras mes")
    assert is_weather_intent("¿Cómo está el clima en Ciudad de México hoy?")


def test_closing_ack_after_news_does_not_research():
    """'ok perfecto' tras una noticia cierra el turno — no repite la búsqueda."""
    tx = _tx(
        ("user", "Dame las últimas noticias de Venezuela"),
        ("agent", "Señor, en Venezuela..."),
        ("user", "ok perfecto"),
    )
    assert resolve_web_search_request("ok perfecto", tx) is None


def test_various_closing_acks_skip_search():
    for ack in ("perfecto", "muy bien", "de acuerdo", "sí gracias", "todo bien", "listo"):
        tx = _tx(
            ("user", "Dame las noticias del día"),
            ("agent", "Señor, hoy..."),
            ("user", ack),
        )
        assert resolve_web_search_request(ack, tx) is None, ack


def test_new_query_after_ack_still_searches():
    """Una consulta nueva real tras una noticia sí debe buscar."""
    tx = _tx(
        ("user", "Dame las noticias de Venezuela"),
        ("agent", "Señor, en Venezuela..."),
        ("user", "ahora dime las noticias de Colombia"),
    )
    req = resolve_web_search_request("ahora dime las noticias de Colombia", tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "colombia" in req["query"].lower()


def test_search_promise_detection():
    from app.services.retell_custom_llm import promised_voice_search_without_result

    assert promised_voice_search_without_result(
        "Permítame investigar eso, señor.",
        user_text="noticias de Venezuela",
    )
    assert not promised_voice_search_without_result(
        "Según las fuentes consultadas, el precio subió a 1300 dólares "
        "y el mercado reaccionó con volatilidad en la sesión de hoy.",
        user_text="precio del bitcoin",
    )
