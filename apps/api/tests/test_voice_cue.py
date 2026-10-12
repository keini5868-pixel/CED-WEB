"""Modo grabación: Ok CED abre, Ok CED stop cierra, el resto no habla."""

from app.services.voice_cue import decide_cue


def test_wake_alone_greets():
    for phrase in ("Ok CED", "ok c", "okay ced", "oye ce", "Ok, SEC"):
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
    action, _text = decide_cue("Ok CED, stop", enabled=True, listening=True)
    assert action == "stop"
    action, _text = decide_cue(
        "y por eso el marketing en redes vende más",
        enabled=True,
        listening=False,
    )
    assert action == "ignore"


def test_while_open_a_normal_question_is_answered():
    action, text = decide_cue(
        "por qué sirven para vender más",
        enabled=True,
        listening=True,
    )
    assert action == "answer"
    assert "vender más" in text


def test_off_mode_does_not_gate():
    action, text = decide_cue("hola, cómo estás", enabled=False, listening=False)
    assert action == "off"
    assert text.startswith("hola")
