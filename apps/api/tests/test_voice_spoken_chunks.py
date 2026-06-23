"""Voice chunk splitting — punctuation-aware cuts."""

from app.services.voice_spoken import chunk_ends_with_punctuation, split_voice_delivery_chunks


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
