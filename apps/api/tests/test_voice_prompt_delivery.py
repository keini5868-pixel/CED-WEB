"""Tests — entrega de prompts largos en voz sin truncar ni repetir."""

from app.services.voice_llm_common import (
    dedupe_voice_reply,
    strip_embedded_prior_assistant,
    voice_generation_limits,
    voice_repeats_last_assistant,
)
from app.services.voice_spoken import is_prompt_creation_request, voice_delivery_chunks


def test_prompt_creation_intent_detects_dooble_studio_request():
    text = (
        "Prepárame un prompt detallado para Dooble Studio, página de cejas, "
        "pestañas y micropigmentación con datos creados por la IA"
    )
    assert is_prompt_creation_request(text)


def test_prompt_creation_gets_high_token_budget():
    text = "Hazme un prompt para Google AI Studio sobre mi salón de cejas"
    max_tokens, timeout = voice_generation_limits(text)
    assert max_tokens >= 2048
    assert timeout >= 28.0


def test_voice_delivery_single_chunk_for_long_prompt():
    text = " ".join(["Sección %s con detalle." % i for i in range(1, 80)])
    chunks = voice_delivery_chunks(text)
    assert len(chunks) == 1
    assert chunks[0][1] is True
    assert len(chunks[0][0]) > 1000


def test_dedupe_voice_reply_removes_duplicate_halves():
    text = "Bloque A.\n\nBloque A."
    assert dedupe_voice_reply(text) == "Bloque A."


def test_dedupe_voice_reply_collapses_identity_stutter():
    stutter = "mi nombre es CED, mi nombre es CED, mi nombre es CED"
    assert dedupe_voice_reply(stutter).lower().count("mi nombre es ced") == 1


def test_voice_repeats_last_assistant():
    repeated = (
        "Para crear un prompt completo para Dooble Studio necesito confirmar algunos detalles: "
        "público objetivo, tono, promociones y llamada a la acción."
    )
    history = [{"role": "assistant", "content": repeated}]
    assert voice_repeats_last_assistant(repeated, history)


def test_voice_repeats_short_identity_line():
    history = [{"role": "assistant", "content": "Mi nombre es CED."}]
    assert voice_repeats_last_assistant("Mi nombre es CED.", history)
    assert voice_repeats_last_assistant("Correcto, mi nombre es CED", history)


def test_strip_embedded_prior_assistant_removes_leading_block():
    prior = (
        "Activize es la bebida de FitLine con NTC para energía celular y enfoque. "
        "Se toma por la mañana y forma parte del Optimal-Set con Restorate y Basics. "
        "En prospección, úsalo para hablar de vitalidad sin inventar comisiones."
    )
    new_topic = (
        "Restorate aporta minerales alcalinos y se toma por la noche. "
        "Es clave en el Optimal-Set junto a Activize para recuperación."
    )
    history = [{"role": "assistant", "content": prior}]
    combined = f"{prior} {new_topic}"
    stripped = strip_embedded_prior_assistant(combined, history)
    assert "Restorate aporta minerales" in stripped
    assert not stripped.startswith("Activize es la bebida")


def test_collapse_stacked_response_variants_keeps_one():
    from app.services.voice_llm_common import collapse_stacked_response_variants

    stacked = (
        "<<<Activize da energía por la mañana con NTC.>>> "
        "Mire, Leroy, Activize es ideal para empezar el día con foco y vitalidad celular."
    )
    out = collapse_stacked_response_variants(stacked)
    assert "<<<" not in out and ">>>" not in out
    # Debe quedar una sola versión (sin marcas TTS).
    assert "Activize" in out
    assert len(out) < len(stacked)


def test_collapse_repeated_paragraph_waste():
    from app.services.voice_llm_common import (
        collapse_stacked_response_variants,
        prefer_single_voice_variant,
    )

    para = (
        "FitLine usa el NTC para llevar nutrientes a nivel celular con respaldo "
        "de más de tres décadas en el mercado global de bienestar."
    )
    stacked = f"{para}\n\n{para}"
    out = collapse_stacked_response_variants(stacked)
    assert out.count("Nutrient") + out.lower().count("ntc") >= 1
    assert out.count("tres décadas") == 1 or out.count("nivel celular") == 1

    primary = "Mire, Activize da energía por la mañana con NTC y enfoque celular."
    rewrite = (
        "Mire, Activize da energía por la mañana con NTC y enfoque celular. "
        "Además conviene tomarlo al despertar."
    )
    single = prefer_single_voice_variant(primary, rewrite)
    assert single.count("Activize da energía") == 1

