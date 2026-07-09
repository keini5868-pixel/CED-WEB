"""Tests — normalización de deltas en streaming."""

from app.services.stream_delta import stream_piece_delta, strip_prefix_overlap


def test_stream_piece_delta_from_cumulative_buffer():
    acc = ""
    pieces = ["Ent", "Entiendo", "Entiendo perfectamente, señor.", "Entiendo perfectamente, señor. Es"]
    deltas = []
    for piece in pieces:
        delta = stream_piece_delta(acc, piece)
        if delta:
            acc += delta
            deltas.append(delta)
    assert acc == "Entiendo perfectamente, señor. Es"
    assert deltas == ["Ent", "iendo", " perfectamente, señor.", " Es"]


def test_stream_piece_delta_incremental_passthrough():
    acc = ""
    for piece in ["Hola", ", señor", "."]:
        d = stream_piece_delta(acc, piece)
        acc += d
    assert acc == "Hola, señor."


def test_strip_prefix_overlap():
    assert strip_prefix_overlap("Un momento, señor.", "Un momento, señor. Listo.") == "Listo."
