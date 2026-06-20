"""Voice chunk splitting — no mid-word cuts."""

from app.services.voice_spoken import split_voice_delivery_chunks


def test_short_text_single_complete_chunk():
    chunks = split_voice_delivery_chunks("Hola, señor. CED operativo.")
    assert len(chunks) == 1
    assert chunks[0] == ("Hola, señor. CED operativo.", True)


def test_long_text_last_chunk_marked_complete():
    text = " ".join(["Oración de prueba número %s." % i for i in range(1, 12)])
    chunks = split_voice_delivery_chunks(text)
    assert chunks
    assert chunks[-1][1] is True
    assert all(part.strip() for part, _ in chunks)
