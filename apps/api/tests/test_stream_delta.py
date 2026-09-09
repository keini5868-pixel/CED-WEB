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


def test_stream_piece_delta_keeps_ced_and_voz_after_same_letters():
    """Regresión: tokens cortos no deben caer porque la letra ya salió en el texto."""
    acc = "Hook 3 — Scarcity + Founding (urgencia).\n\nGUION VIDEO — ACCIÓN\n"
    assert stream_piece_delta(acc, "C") == "C"
    acc += "C"
    assert stream_piece_delta(acc, "ED") == "ED"
    acc += "ED"
    assert stream_piece_delta(acc, " no solo genera contenido. ") == " no solo genera contenido. "
    acc += " no solo genera contenido. "
    assert stream_piece_delta(acc, "V") == "V"
    acc += "V"
    assert stream_piece_delta(acc, "oz en off") == "oz en off"
    acc += "oz en off"
    assert "CED" in acc
    assert "Voz en off" in acc


def test_stream_piece_delta_still_skips_long_echo_substring():
    acc = "Perfecto, señor. Aquí el guion completo del video para Instagram."
    assert stream_piece_delta(acc, "guion completo del video") == ""
