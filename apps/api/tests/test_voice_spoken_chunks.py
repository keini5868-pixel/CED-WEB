"""Voice chunk splitting — punctuation-aware cuts."""

from app.services.voice_response_guard import guard_voice_response
from app.services.voice_spoken import (
    chunk_ends_with_punctuation,
    finalize_voice_delivery_text,
    normalize_numbers_for_speech,
    split_voice_delivery_chunks,
    strip_voice_filler_prefix,
)


def test_normalize_numbers_for_speech_removes_thousand_commas():
    assert normalize_numbers_for_speech("1,300 muertos") == "1300 muertos"
    assert normalize_numbers_for_speech("Hay 12,345,678 casos") == "Hay 12345678 casos"


def test_guard_voice_response_normalizes_numbers():
    safe, blocked = guard_voice_response("Se reportan 1,300 víctimas confirmadas.")
    assert not blocked
    assert safe == "Se reportan 1300 víctimas confirmadas."


def test_short_text_single_complete_chunk():
    chunks = split_voice_delivery_chunks("Hola, señor. CED operativo.")
    assert len(chunks) == 1
    assert chunks[0] == ("Hola, señor. CED operativo.", True)
    assert chunk_ends_with_punctuation(chunks[0][0])


def test_long_text_last_chunk_marked_complete():
    text = " ".join(["Oración de prueba número %s." % i for i in range(1, 12)])
    chunks = split_voice_delivery_chunks(text)
    assert chunks
    assert chunks[-1][1] is True
    assert all(part.strip() for part, _ in chunks)


def test_chunks_end_with_punctuation_when_possible():
    long_clause = (
        "El Amazon Prime Day 2026 ha comenzado en México, ofreciendo importantes descuentos "
        "en dispositivos, smartphones y tecnología para el hogar, con ofertas que duran "
        "varios días y cubren múltiples categorías de productos electrónicos."
    )
    text = f"{long_clause} Además, las promociones incluyen envío gratuito en pedidos seleccionados."
    chunks = split_voice_delivery_chunks(text, max_chunk=120)
    assert len(chunks) >= 2
    for part, _ in chunks[:-1]:
        assert chunk_ends_with_punctuation(part) or part.rstrip().endswith(",")


def test_long_sentence_splits_on_comma_not_mid_word():
    sent = (
        "Primera idea muy extensa sobre marketing digital y ventas en redes sociales, "
        "segunda idea sobre prospección automatizada en Instagram, "
        "tercera idea sobre funnels de conversión y cierre de clientes potenciales."
    )
    chunks = split_voice_delivery_chunks(sent, max_chunk=90)
    assert chunks
    for part, _ in chunks:
        assert " " not in part or not part.endswith(" ")
        assert not part.endswith(" en") and not part.endswith(" de")


def test_strip_voice_filler_prefix_removes_duplicate_hold():
    raw = "Un momento, señor. Un momento, señor. Algunas investigaciones sugieren."
    assert strip_voice_filler_prefix(raw).startswith("Algunas investigaciones")


def test_finalize_voice_delivery_text_trims_incomplete_tail():
    raw = "Me encuentro muy bien, gracias por preguntar. ¿En qué"
    out = finalize_voice_delivery_text(raw)
    assert out == "Me encuentro muy bien, gracias por preguntar."
    assert chunk_ends_with_punctuation(out)
