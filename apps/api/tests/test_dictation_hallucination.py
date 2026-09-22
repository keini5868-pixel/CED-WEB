from app.services.chat_multimedia import sanitize_dictation_transcript


def test_silence_amara_is_empty():
    assert sanitize_dictation_transcript("Subtítulo Amara") == ""
    assert sanitize_dictation_transcript("Subtítulos realizados por la comunidad de Amara.org") == ""
    assert sanitize_dictation_transcript("amara.org") == ""
    assert sanitize_dictation_transcript("Thanks for watching") == ""
    assert sanitize_dictation_transcript("") == ""


def test_real_dictation_is_kept():
    assert (
        sanitize_dictation_transcript("Hola CED, arma un copy de FitLine")
        == "Hola CED, arma un copy de FitLine"
    )
