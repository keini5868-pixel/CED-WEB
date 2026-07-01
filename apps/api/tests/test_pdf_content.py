"""Tests — contenido completo en PDF y filtros de chat."""

from app.services.pdf_report import resolve_pdf_content
from app.services.text_chat import _contains_internal_kb_leak, _dedupe_chat_reply


def test_resolve_pdf_content_uses_previous_assistant_text():
    title = "Calendario de contenido semanal"
    body = title
    fallback = (
        "Lunes: post educativo sobre cejas.\n"
        "Martes: reel de antes/después.\n"
        "Miércoles: tips de micropigmentación.\n"
        "Jueves: testimonial.\n"
        "Viernes: promoción fin de semana."
    )
    resolved = resolve_pdf_content(title, body, fallback_texts=[fallback])
    assert "Lunes" in resolved
    assert "Viernes" in resolved
    assert resolved != title


def test_dedupe_chat_reply_removes_exact_duplicate_halves():
    text = "Bloque A.\n\nBloque A."
    assert _dedupe_chat_reply(text) == "Bloque A."


def test_internal_kb_leak_patterns():
    leaked = (
        "Conocimiento interno CED (priorizar sobre suposiciones):\n"
        "- [Marketing digital] SEO básico para negocios: ..."
    )
    assert _contains_internal_kb_leak(leaked)
