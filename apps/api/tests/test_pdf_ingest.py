"""Unit tests — inbound PDF text extract."""

from __future__ import annotations

import io

import pytest

from app.services.pdf_ingest import (
    PdfIngestError,
    extract_pdf_text,
    format_pdf_for_llm,
    user_display_for_pdf,
)


def _make_simple_pdf(text: str = "Hola CED, este es un PDF de prueba.") -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, text)
    out = pdf.output()
    return bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out)


def test_extract_pdf_text_ok():
    data = _make_simple_pdf("Contrato de servicios FitLine 2026.")
    result = extract_pdf_text(data, filename="contrato.pdf")
    assert result.page_count >= 1
    assert "FitLine" in result.text or "Contrato" in result.text
    assert result.filename.endswith(".pdf")


def test_extract_rejects_non_pdf():
    with pytest.raises(PdfIngestError):
        extract_pdf_text(b"not a pdf", filename="x.pdf")


def test_extract_rejects_empty():
    with pytest.raises(PdfIngestError):
        extract_pdf_text(b"", filename="x.pdf")


def test_format_and_display():
    data = _make_simple_pdf("Contenido largo del informe comercial.")
    extracted = extract_pdf_text(data, filename="informe.pdf")
    llm = format_pdf_for_llm(extracted, "Resume esto")
    assert "DOCUMENTO PDF ADJUNTO" in llm
    assert "Resume esto" in llm
    assert "informe.pdf" in user_display_for_pdf("informe.pdf", "Resume esto")


def test_ingest_route(client_factory=None):
    """Smoke: POST /v1/pdf/ingest with auth override."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    app.dependency_overrides[
        __import__("app.deps.auth", fromlist=["require_user_id"]).require_user_id
    ] = lambda: "user-test-1"
    client = TestClient(app)
    data = _make_simple_pdf(
        "Texto de ingest API para CED. Documento de prueba con contenido suficiente."
    )
    files = {"pdf": ("nota.pdf", io.BytesIO(data), "application/pdf")}
    res = client.post("/v1/pdf/ingest", files=files)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("ok") is True
    assert body.get("text")
    assert body.get("filename", "").endswith(".pdf")
