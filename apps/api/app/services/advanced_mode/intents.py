"""Detección de intención — solo reglas locales de Modo Avanzado (sin orquestador)."""

from __future__ import annotations

import re
from typing import Any

from app.services.text_chat import (
    is_generate_image_intent,
    is_pdf_intent,
    parse_generate_image_prompt,
    resolve_pdf_request,
)

# Investigación / hechos actuales deben usar search_web — no Claude sin grounding.
# Antes «investiga quién ganó…» (sin «en internet») caía a stream plano → alucinaciones.
_EXPLICIT_WEB = re.compile(
    r"\b("
    r"busca(?:r|me)?\s+(en\s+)?(internet|la\s+web|google|noticias)|"
    r"investiga(?:r|me)?(?:\s+(en\s+)?(internet|la\s+web))?"
    r"|noticias?\s+(de|sobre|del|hoy|actuales)"
    r"|clima|tiempo\s+en|titulares|última\s+hora"
    r"|datos?\s+(actuales?|recientes?|en\s+tiempo\s+real)"
    r"|verifica(?:r)?\s+(en\s+)?(internet|la\s+web|fuentes)"
    r")\b",
    re.I,
)


def needs_advanced_full_pipeline(text: str, history_rows: list[dict[str, Any]]) -> bool:
    """PDF o búsqueda web explícita → pipeline completo (imagen tiene ruta propia en stream)."""
    from app.services.chat_intents import resolve_pdf_detail_for_turn

    if is_pdf_intent(text):
        return True
    if resolve_pdf_request(text, history_rows):
        return True
    # Follow-up "completo"/"breve" tras la pregunta de extensión — NO stream plano
    # (Claude alucinaba "PDF listo" sin tool / sin adjunto).
    detail = resolve_pdf_detail_for_turn(text, history_rows)
    if detail in ("brief", "full", "ask"):
        return True
    if _EXPLICIT_WEB.search(text.strip()):
        return True
    return False
