"""Tests — detección PDF en chat y resolución desde historial."""

from __future__ import annotations

from app.services.chat_intents import (
    is_generate_image_intent,
    is_pdf_intent,
    mentions_pdf,
    resolve_pdf_request,
)
from app.services.text_chat import (
    _hallucinated_generar_pdf_fields,
    _has_hallucinated_tool_code,
)


def test_is_pdf_intent_dame_esto_en_pdf():
    assert is_pdf_intent("ok dame esto en un pdf")
    assert is_pdf_intent("pon lo en un pdf por favor")


def test_pdf_priority_over_image_intent():
    msg = "genérame un PDF con un resumen de la historia del alquimista"
    assert mentions_pdf(msg)
    assert is_pdf_intent(msg)
    assert not is_generate_image_intent(msg)
    assert is_pdf_intent("créame un PDF")
    assert not is_generate_image_intent("créame un PDF")


def test_resolve_pdf_request_uses_last_assistant_plan():
    history = [
        {"role": "user", "content": "haz un plan semanal"},
        {
            "role": "assistant",
            "content": (
                "### Plan Semanal de Estrategia para el Lanzamiento de CED\n\n"
                "**Lunes:** Reel educativo.\n**Martes:** Carrusel de diseño.\n"
            ),
        },
    ]
    req = resolve_pdf_request("ok dame esto en un pdf", history)
    assert req is not None
    title, body = req
    assert "Plan" in title
    assert "Lunes" in body
    assert "Martes" in body


def test_hallucinated_generar_pdf_fields_extracts_content():
    reply = (
        '```tool_code\nprint(generar_pdf(content="Plan Semanal de Estrategia", '
        'title="Plan Semanal de Estrategia para el Lanzamiento de CED"))\n```'
    )
    assert _has_hallucinated_tool_code(reply)
    fields = _hallucinated_generar_pdf_fields(reply)
    assert fields is not None
    title, content = fields
    assert "Plan Semanal" in title
    assert "Plan Semanal" in content
