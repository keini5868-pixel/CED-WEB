"""Plantillas de guion del usuario: se siguen al pie de la letra, sin saltarse pasos."""

from __future__ import annotations

from app.domain.ced_script_blueprints import (
    CED_SCRIPT_BLUEPRINTS,
    CED_VIDEO_SCRIPT_FORMATS,
    detect_script_blueprint,
    detect_script_duration,
    is_script_format_catalog,
    is_video_content_calendar,
    script_blueprints_block,
    wants_script_blueprints,
    with_script_blueprints_if_needed,
)
from app.services.text_chat import (
    CHAT_SYSTEM_MAX_CHARS,
    _build_chat_system_light,
    _trim_system,
)


def test_blueprints_keep_every_literal_step():
    body = CED_SCRIPT_BLUEPRINTS
    for step in (
        "Gancho emocional",
        "Punto de quiebre",
        "Lección o cambio profundo",
        "CTA natural",
        "Problema común",
        "Consejo práctico",
        "Gancho con una meta o resultado deseable",
        "Prueba social o experiencia real",
        "1 a 3 tips accionables",
        "Promesa de cambio",
        "Reacción al comentario",
        "Señalar el problema o error",
        "Invitación a dejar más dudas",
        "Gancho que haga dudar",
        "Síntomas o señales",
        "Hook fuerte",
        "Contexto del problema",
        "Por qué decidí crear esta serie",
        "Qué van a aprender en los próximos videos",
        "CTA para seguir la serie",
        "Gancho con resultado o transformación",
        "Presentación directa del producto o servicio",
        "Gancho sorpresivo o cómico",
        "Remate o punchline",
        "Gancho mostrando el resultado final primero",
        "Proceso paso a paso acelerado o resumido",
        "Gancho con una pregunta o frase que invite a pensar",
        "La reflexión o aprendizaje central",
    ):
        assert step in body, step


def test_blueprints_forbid_inventing_other_structures():
    body = CED_SCRIPT_BLUEPRINTS.lower()
    assert "prohibido inventar una estructura alternativa" in body
    assert "5 opciones de título" in CED_SCRIPT_BLUEPRINTS
    assert "5 opciones de hook" in CED_SCRIPT_BLUEPRINTS


def test_extras_never_postponed_until_the_user_gives_the_topic():
    body = CED_SCRIPT_BLUEPRINTS.lower()
    assert "los extras van siempre" in body
    assert "[corchetes]" in body
    assert "cuando me compartas el tema" in body  # ejemplo de lo prohibido


def test_detect_each_blueprint_kind():
    assert detect_script_blueprint("dame la estructura para una mini serie") == "mini_serie"
    assert detect_script_blueprint("guion tipo historia que vende") == "historia"
    assert detect_script_blueprint("guion con problema invisible") == "problema_invisible"
    assert detect_script_blueprint("quiero un guion de autoridad") == "autoridad"
    assert detect_script_blueprint("guion educativo para instagram") == "educativo"
    assert detect_script_blueprint("guion para responder un comentario") == "comentario"
    assert detect_script_blueprint("hazme un plan de finanzas") is None


def test_wants_blueprints_only_on_script_turns():
    assert wants_script_blueprints("dame la estructura para una mini serie")
    assert wants_script_blueprints("hazme un guion educativo para Instagram")
    assert wants_script_blueprints("quiero un guion de autoridad para mi nicho")
    assert wants_script_blueprints("necesito un guion para un reel")
    assert wants_script_blueprints("hola cómo estás") is False
    assert wants_script_blueprints("dame un copy para vender mi curso") is False


def test_blueprints_go_first_and_only_once():
    once = with_script_blueprints_if_needed("BASE", "dame un guion para un reel")
    assert once.startswith("# PLANTILLAS OFICIALES DE GUION")
    assert once.endswith("BASE")
    twice = with_script_blueprints_if_needed(once, "dame un guion para un reel")
    assert twice.count("PLANTILLAS OFICIALES DE GUION") == 1


def test_ten_formats_are_complete():
    assert len(CED_VIDEO_SCRIPT_FORMATS) == 10
    numbers = [bp.number for bp in CED_VIDEO_SCRIPT_FORMATS]
    assert numbers == list(range(1, 11))
    for bp in CED_VIDEO_SCRIPT_FORMATS:
        assert bp.ask_for.strip(), bp.key
        assert len(bp.structure) >= 4, bp.key
        assert bp.tone.strip(), bp.key
        assert bp.patterns, bp.key


def test_detect_the_four_new_formats():
    assert detect_script_blueprint("quiero un guion de qué vendo") == "que_vendes"
    assert detect_script_blueprint("un guion entretenido y gracioso") == "entretenimiento"
    assert detect_script_blueprint("guion demostrativo de mi proceso") == "demostrativo"
    assert detect_script_blueprint("un guion reflexivo sobre lo que aprendí") == "reflexivo"
    # «historia que vende» no debe caer en el formato de venta directa.
    assert detect_script_blueprint("guion de historia que vende") == "historia"


def test_detect_requested_duration():
    assert detect_script_duration("un guion de 30s") == 30
    assert detect_script_duration("guion educativo de 40 segundos") == 40
    assert detect_script_duration("hazlo de 1 minuto") == 60
    assert detect_script_duration("que dure minuto y medio") == 90
    assert detect_script_duration("hazme un guion educativo") is None


def test_block_asks_which_format_when_unknown():
    block = script_blueprints_block(None)
    assert "Los 10 formatos" in block
    assert "10 — Reflexivo" in block
    assert "Pregunta cuál de los 10 quiere" in block


def test_block_carries_only_the_requested_format():
    block = script_blueprints_block("demostrativo", seconds=30)
    assert "Gancho mostrando el resultado final primero" in block
    assert "Datos a pedir:" in block
    assert "75 palabras" in block  # 30 s × 2,5 palabras/s
    assert "Punto de quiebre" not in block  # la ficha de Historia no viaja


def test_voice_prompt_carries_the_blueprint():
    from app.services.voice_llm_common import build_base_voice_system

    voice = build_base_voice_system("user-test", "hazme un guion demostrativo para un reel")
    assert "Proceso paso a paso acelerado o resumido" in voice


def test_chat_prompt_keeps_blueprints_after_trim():
    system = _build_chat_system_light("user-test", "dame la estructura para una mini serie")
    assert "Por qué decidí crear esta serie" in system
    # El system se recorta por el final: el bloque debe sobrevivir al truncado.
    assert "Por qué decidí crear esta serie" in _trim_system(system)
    assert len(script_blueprints_block("mini_serie")) < CHAT_SYSTEM_MAX_CHARS


def test_unspecified_format_asks_which_of_ten():
    system = _build_chat_system_light("user-test", "necesito un guion para un reel")
    assert "Los 10 formatos" in system
    assert "Pregunta cuál de los 10 quiere" in system
    assert "## 01 — Historia" not in system


SALON_CALENDAR = (
    "quiero hacer una estrutura de aqui al 24 3 videos por semana "
    "todo es para un salon de belleza"
)
FORMAT_INDEX = (
    "quiero usar esta estrutura Índice de formatos\n"
    "01 - Historia: Storytelling que vende sin vender.\n"
    "02- Qué vendes: Presentación directa de tu producto o servicio.\n"
    "03- Educativo: Enseña algo útil y práctico a tu audiencia.\n"
    "10- Reflexivo: Comparte un aprendizaje o una reflexión personal."
)


def test_month_calendar_uses_all_ten_not_one_script():
    assert is_video_content_calendar(SALON_CALENDAR)
    assert wants_script_blueprints(SALON_CALENDAR)
    assert detect_script_blueprint(SALON_CALENDAR) is None
    block = with_script_blueprints_if_needed("BASE", SALON_CALENDAR)
    assert "CALENDARIO DE VIDEOS" in block
    assert "PROHIBIDO abrir publicación" in block
    assert "Gancho emocional" in block
    assert "Pregunta cuál de los 10 quiere" not in block


def test_pasted_format_index_is_a_catalog_not_historia():
    assert is_script_format_catalog(FORMAT_INDEX)
    assert detect_script_blueprint(FORMAT_INDEX) is None
    block = with_script_blueprints_if_needed("BASE", FORMAT_INDEX)
    assert "CALENDARIO DE VIDEOS" in block
    assert "## 01 — Historia" not in block


def test_advanced_mode_gets_the_requested_format():
    from app.services.advanced_mode.service import _stream_system_with_clock

    system = _stream_system_with_clock(
        "user-test",
        "hazme un guion reflexivo de 40 segundos",
    )
    assert "Gancho con una pregunta o frase que invite a pensar" in system
    assert "unas 100 palabras" in system
