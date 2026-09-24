"""Plantillas de guion del usuario: se siguen al pie de la letra, sin saltarse pasos."""

from __future__ import annotations

from app.domain.ced_script_blueprints import (
    CED_SCRIPT_BLUEPRINTS,
    detect_script_blueprint,
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


def test_chat_prompt_keeps_blueprints_after_trim():
    system = _build_chat_system_light("user-test", "dame la estructura para una mini serie")
    assert "Por qué decidí crear esta serie" in system
    # El system se recorta por el final: el bloque debe sobrevivir al truncado.
    assert "Por qué decidí crear esta serie" in _trim_system(system)
    assert len(CED_SCRIPT_BLUEPRINTS) < CHAT_SYSTEM_MAX_CHARS
