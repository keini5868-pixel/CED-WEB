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


def test_resolve_pdf_request_uses_assistant_news_for_esa_informacion():
    history = [
        {
            "role": "assistant",
            "content": (
                "Un poderoso tornado EF2 azotó la provincia central de Hubei en China, "
                "dejando once fallecidos y más de trescientas heridas."
            ),
        },
    ]
    req = resolve_pdf_request("¿me puedes crear un PDF con esa información?", history)
    assert req is not None
    title, body = req
    assert "Hubei" in body or "tornado" in body.lower()
    assert title != "Documento CED"
    assert "Tornado" in title or "Hubei" in title


def test_infer_pdf_title_from_tornado_content():
    from app.services.chat_intents import infer_pdf_title

    title = infer_pdf_title(
        "PDF con esa información",
        "Un poderoso tornado EF2 azotó Hubei en China dejando once fallecidos.",
    )
    assert "Tornado" in title
    assert "China" in title or "Hubei" in title


def test_parse_pdf_request_does_not_use_hola_placeholder():
    from app.services.chat_intents import parse_pdf_request

    title, body = parse_pdf_request("genera un pdf")
    assert body != "Hola"


def test_resolve_pdf_skips_filler_assistant_closing():
    history = [
        {
            "role": "assistant",
            "content": (
                "La neuroplasticidad es la capacidad del cerebro de reorganizar sus conexiones "
                "neuronales a lo largo de la vida, permitiendo aprender y recuperarse de lesiones."
            ),
        },
        {
            "role": "assistant",
            "content": "¿Hay algo más en lo que le pueda ayudar?",
        },
    ]
    req = resolve_pdf_request("pon eso en un pdf", history)
    assert req is not None
    title, body = req
    assert "neuroplasticidad" in body.lower()
    assert "algo más" not in title.lower()
    assert "algo más" not in body.lower()


def test_pdf_success_message_mentions_historial():
    from app.services.text_chat import _normalize_pdf_tool_reply, _pdf_success_message

    msg = _pdf_success_message("Tornado EF2 en Hubei, China")
    assert "historial" in msg.lower()
    assert "Tornado" in msg
    normalized = _normalize_pdf_tool_reply(
        "Listo. PDF generado. Usa el botón Descargar abajo.",
        {"file_id": "x1", "title": "Informe"},
    )
    assert "historial" in normalized.lower()
    assert "Descargar abajo" not in normalized
