"""Tests — extensión PDF (pregunta resumen vs completo) y aviso de texto en imágenes."""

from __future__ import annotations

from unittest.mock import patch

from app.services.chat_intents import (
    PDF_DETAIL_CLARIFY_QUESTION,
    is_pdf_intent,
    pdf_detail_level,
    resolve_pdf_detail_for_turn,
)
from app.services.copy_quality import with_image_text_disclaimer
from app.services.pdf_report import _compose_pdf_prompt
from app.services.text_chat import _try_direct_pdf_from_context


def test_ambiguous_pdf_asks_before_generating():
    msg = "genera un PDF con consejos del alquimista"
    assert pdf_detail_level(msg) is None
    assert resolve_pdf_detail_for_turn(msg, []) == "ask"

    with patch("app.services.text_chat._execute_direct_pdf") as mock_exec:
        out = _try_direct_pdf_from_context(
            "u1",
            text=msg,
            history=[],
            conversation_id="c1",
        )
    assert out is not None
    reply, attachment = out
    assert "resumen breve" in reply.lower()
    assert "completo" in reply.lower()
    assert attachment == {}
    mock_exec.assert_not_called()


def test_explicit_brief_pdf_generates_without_ask():
    msg = "genera un PDF resumen breve con consejos del alquimista"
    assert resolve_pdf_detail_for_turn(msg, []) == "brief"

    with patch(
        "app.services.text_chat._execute_direct_pdf",
        return_value=("Listo. PDF generado.", {"file_id": "x", "title": "Consejos"}),
    ) as mock_exec:
        out = _try_direct_pdf_from_context(
            "u1",
            text=msg,
            history=[],
            conversation_id="c1",
        )
    assert out is not None
    assert out[1].get("file_id") == "x"
    assert mock_exec.call_args.kwargs["detail_level"] == "brief"


def test_explicit_full_pdf_generates_without_ask():
    msg = "genera un PDF completo y detallado sobre el alquimista"
    assert is_pdf_intent(msg)
    assert resolve_pdf_detail_for_turn(msg, []) == "full"


def test_answer_after_clarify_uses_prior_request():
    history = [
        {"role": "user", "content": "genera un PDF con consejos del alquimista"},
        {"role": "assistant", "content": PDF_DETAIL_CLARIFY_QUESTION},
    ]
    assert resolve_pdf_detail_for_turn("resumen breve", history) == "brief"
    assert resolve_pdf_detail_for_turn("el completo", history) == "full"

    with patch(
        "app.services.text_chat._execute_direct_pdf",
        return_value=("Listo. PDF generado.", {"file_id": "y", "title": "Consejos"}),
    ) as mock_exec:
        out = _try_direct_pdf_from_context(
            "u1",
            text="breve",
            history=history,
            conversation_id="c1",
        )
    assert out is not None
    assert mock_exec.call_args.kwargs["detail_level"] == "brief"
    assert "alquimista" in mock_exec.call_args.kwargs["user_request"].lower()


def test_completo_followup_is_pdf_detail_full():
    """Regresión prod: 'completo' no es is_pdf_intent pero SÍ debe generar PDF."""
    from app.services.advanced_mode.intents import needs_advanced_full_pipeline

    history = [
        {"role": "user", "content": "genera un pdf con esa información"},
        {"role": "assistant", "content": PDF_DETAIL_CLARIFY_QUESTION},
    ]
    assert is_pdf_intent("completo") is False
    assert resolve_pdf_detail_for_turn("completo", history) == "full"
    assert needs_advanced_full_pipeline("completo", history) is True
    assert needs_advanced_full_pipeline("completo", []) is False


def test_keepalive_yields_done_when_fn_already_finished():
    """Regresión prod avanzado: clarify PDF instantáneo no debe perderse (result=None)."""
    from app.services.advanced_mode.service import _iter_blocking_with_keepalives

    kinds = []
    payload = None
    for kind, value in _iter_blocking_with_keepalives(lambda: {"ok": True, "fast": 1}):
        kinds.append(kind)
        if kind == "done":
            payload = value
    assert "done" in kinds
    assert payload == {"ok": True, "fast": 1}


def test_compose_prompt_brief_by_default():
    prompt = _compose_pdf_prompt(
        title="Consejos",
        user_request="PDF del alquimista",
        detail_level="brief",
    )
    assert "RESUMEN BREVE" in prompt
    assert "350 palabras" not in prompt
    full = _compose_pdf_prompt(
        title="Consejos",
        user_request="PDF del alquimista",
        detail_level="full",
    )
    assert "COMPLETO" in full


def test_image_text_disclaimer_when_quote_requested():
    reply = with_image_text_disclaimer(
        "Listo. Aquí está tu imagen.",
        'genera un pergamino con el texto "Sigue tu leyenda personal"',
    )
    assert "aviso" in reply.lower()
    assert "legible" in reply.lower()
    assert "Listo" in reply

    plain = with_image_text_disclaimer(
        "Listo. Aquí está tu imagen.",
        "genera una imagen de un bosque al atardecer",
    )
    assert "aviso" not in plain.lower()
