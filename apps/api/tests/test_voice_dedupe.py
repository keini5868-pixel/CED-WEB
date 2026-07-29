"""Tests — deduplicación global de respuestas de voz."""

from app.services.voice_llm_common import (
    is_duplicate_voice_delivery,
    is_stt_echo_of_assistant,
)
from app.services.voice_spoken import VOICE_NEWS_MAX_CHARS, fit_voice_spoken, voice_spoken_limit_for_kind


def test_duplicate_voice_delivery_same_news_prefix():
    first = (
        "Señor, sobre su consulta: Hoy, 1 de julio de 2026, Donald Trump enfrenta un revés "
        "en la Corte Suprema."
    )
    second = (
        "Señor, sobre su consulta: Hoy, 1 de julio de 2026, Donald Trump enfrenta un revés "
        "en la Corte Suprema de Estados Unidos, que rechazó su intento."
    )
    assert is_duplicate_voice_delivery(first, second)


def test_duplicate_voice_delivery_short_identity():
    assert is_duplicate_voice_delivery("Mi nombre es CED.", "Mi nombre es CED")
    assert is_duplicate_voice_delivery(
        "Correcto, señor. Mi nombre es CED.",
        "Mi nombre es CED.",
    )


def test_stt_echo_of_assistant_identity_loop():
    spoken = "Mi nombre es CED."
    assert is_stt_echo_of_assistant("mi nombre es CED", spoken)
    assert is_stt_echo_of_assistant("Mi nombre es CED.", spoken)
    assert not is_stt_echo_of_assistant("generame una imagen de un gato", spoken)


def test_news_spoken_limit_allows_longer_brief():
    assert voice_spoken_limit_for_kind("news") == VOICE_NEWS_MAX_CHARS
    long_text = "Noticia. " * 400
    fitted = fit_voice_spoken(long_text, max_chars=voice_spoken_limit_for_kind("news"))
    assert len(fitted) > 720
    assert fitted.endswith(".")
