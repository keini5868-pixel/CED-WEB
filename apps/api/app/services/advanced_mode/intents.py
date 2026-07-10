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

_EXPLICIT_WEB = re.compile(
    r"\b(busca(r|me)?\s+(en\s+)?(internet|la web|google)|"
    r"investiga(r|me)?\s+(en\s+)?(internet|la web)|"
    r"noticias?\s+(de|sobre|del)|"
    r"clima|tiempo\s+en|titulares|última hora)\b",
    re.I,
)


def needs_advanced_full_pipeline(text: str, history_rows: list[dict[str, Any]]) -> bool:
    """PDF o búsqueda web explícita → pipeline completo (imagen tiene ruta propia en stream)."""
    if is_pdf_intent(text):
        return True
    if resolve_pdf_request(text, history_rows):
        return True
    if _EXPLICIT_WEB.search(text.strip()):
        return True
    return False
