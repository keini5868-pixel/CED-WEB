"""Modo grabación: Ok CED abre, Ok CED stop cierra, el resto no habla."""

from app.services.voice_cue import decide_cue


def test_wake_alone_greets():
    for phrase in (
        "Ok CED",
        "ok c",
        "okay ced",
        "oye ce",
        "Ok, SEC",
        "okay set",
        "okey seth",
        "oye said",
    ):
        action, text = decide_cue(phrase, enabled=True, listening=False)
        assert action == "greet", phrase
        assert text == ""


def test_wake_with_question_answers_without_the_name():
    action, text = decide_cue(
        "Ok CED dime en un resumen por qué sirven las estrategias de marketing",
        enabled=True,
        listening=False,
    )
    assert action == "answer"
    assert text.lower().startswith("dime en un resumen")
    assert "ok ced" not in text.lower()


def test_stop_closes_and_presentation_stays_silent():
    for phrase in (
        "Ok CED, stop",
        "okay, set, stop",
        "okay seth stop",
        "ok sec alto",
        "stop",
        "etop",
        "e top",
        "alto",
        "cállate",
    ):
        action, _text = decide_cue(phrase, enabled=True, listening=True)
        assert action == "stop", phrase
    action, _text = decide_cue("stop", enabled=True, listening=False)
    assert action == "stop"
    action, _text = decide_cue(
        "y por eso el marketing en redes vende más",
        enabled=True,
        listening=False,
    )
    assert action == "ignore"
    action, text = decide_cue(
        "hay que hacer un stop en la campaña de redes porque vende más",
        enabled=True,
        listening=True,
    )
    assert action == "answer"
    assert "campaña" in text or "campana" in text.lower()


def test_while_open_a_normal_question_is_answered():
    action, text = decide_cue(
        "por qué sirven para vender más",
        enabled=True,
        listening=True,
    )
    assert action == "answer"
    assert "vender más" in text


def test_stop_at_the_end_of_a_longer_line_still_closes():
    action, _text = decide_cue(
        "explicame el marketing y ya stop",
        enabled=True,
        listening=True,
    )
    assert action == "stop"
    action, text = decide_cue(
        "hay que hacer un stop en la campaña de redes porque vende más",
        enabled=True,
        listening=True,
    )
    assert action == "answer"
    assert "vende" in text


def test_off_mode_does_not_gate():
    action, text = decide_cue("hola, cómo estás", enabled=False, listening=False)
    assert action == "off"
    assert text.startswith("hola")
