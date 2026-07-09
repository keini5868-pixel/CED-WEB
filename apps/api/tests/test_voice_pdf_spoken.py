"""Tests — sanitización de narración PDF en voz."""

from app.services.voice_spoken import sanitize_pdf_delivery_text


def test_sanitize_pdf_removes_where_to_save_prompt():
    raw = "PDF listo, señor. Título: Documento CED. ¿Dónde desea guardarlo?"
    cleaned = sanitize_pdf_delivery_text(raw)
    assert "guardarlo" not in cleaned.lower()
    assert "historial" in cleaned.lower()


def test_sanitize_pdf_keeps_historial_when_present():
    raw = "PDF listo, señor. Título: Tornado en Hubei. Ya está en su historial."
    assert sanitize_pdf_delivery_text(raw) == raw
