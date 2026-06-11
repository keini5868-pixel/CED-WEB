"""Visión + búsqueda web — identifica imagen y consulta Tavily."""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

from app.config import get_settings
from app.services.tavily_search import tavily_answer, tavily_search

logger = logging.getLogger(__name__)

VISION_MODEL = "gemini-2.5-flash"

ANALYZE_PROMPT_DEFAULT = (
    "Eres la visión de CED para Keini Castillo. Mira la imagen con atención.\n"
    "Responde en español latinoamericano, claro y directo (máx. 4 oraciones cortas):\n"
    "1) QUÉ ES — nombre concreto del objeto, producto, persona, texto o escena principal.\n"
    "2) DETALLE RELEVANTE — color, marca, texto legible, cantidad, acción o contexto útil.\n"
    "3) Si hay texto visible, transcríbelo entre comillas.\n"
    "PROHIBIDO: 'parece que', 'no estoy seguro', 'podría ser'. Di lo que SÍ ves."
)


def _decode_image(image_b64: str) -> bytes:
    raw = image_b64.strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def _gemini_vision(image_bytes: bytes, prompt: str, *, max_tokens: int = 320) -> str:
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return ""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.12,
                max_output_tokens=max_tokens,
            ),
        )
        return (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.error("[VISION] gemini %s", exc)
        return ""


def _identify_subject(image_bytes: bytes, question: str = "") -> str:
    prompt = (
        question.strip()
        or "Identifica el objeto, producto, marca o texto principal en esta imagen. "
        "Responde en UNA frase corta en español, ideal para buscar en Google. "
        "Ejemplo: 'procesador AMD Ryzen' o 'logo Nike'. Sin markdown."
    )
    text = _gemini_vision(image_bytes, prompt, max_tokens=128)
    text = re.sub(r"^(es|se ve|parece)\s+(un|una)\s+", "", text, flags=re.I)
    return text[:200]


def _spoken(text: str, limit: int = 420) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    if not t:
        return ""
    return t[:limit]


def analyze_image(
    image_b64: str,
    *,
    question: str = "",
) -> dict[str, Any]:
    """Describe lo visible con precisión — sin buscar en internet."""
    try:
        image_bytes = _decode_image(image_b64)
    except Exception:
        return {"ok": False, "error": "Imagen inválida"}

    user_q = question.strip()
    prompt = ANALYZE_PROMPT_DEFAULT
    if user_q and len(user_q) > 8:
        prompt = f"{ANALYZE_PROMPT_DEFAULT}\n\nPregunta de Keini: {user_q}"

    subject = _gemini_vision(image_bytes, prompt, max_tokens=380)
    if not subject:
        return {"ok": False, "error": "No pude analizar la imagen"}
    summary = _spoken(subject, limit=580)
    return {"ok": True, "summary": summary, "subject": summary[:200]}


def vision_search_web(
    image_b64: str,
    *,
    question: str = "",
) -> dict[str, Any]:
    """Identifica imagen → Tavily (campo answer + results)."""
    try:
        image_bytes = _decode_image(image_b64)
    except Exception:
        return {"ok": False, "error": "Imagen inválida"}

    subject = _identify_subject(image_bytes, question)
    if not subject:
        return {"ok": False, "error": "No identifiqué qué buscar en la imagen"}

    query = subject
    if question.strip():
        query = f"{subject} {question.strip()}"

    answer = tavily_answer(query)
    if answer and len(answer) >= 36:
        logger.info("[VISION:WEB] tavily answer len=%s q=%s", len(answer), query[:60])
        return {
            "ok": True,
            "summary": _spoken(answer),
            "query": query,
            "subject": subject,
            "source": "tavily",
        }

    rows = tavily_search(query, max_results=5)
    for row in rows:
        content = str(row.get("content") or "").strip()
        if len(content) >= 40:
            return {
                "ok": True,
                "summary": _spoken(content[:380]),
                "query": query,
                "subject": subject,
                "source": "tavily",
            }

    settings = get_settings()
    if not settings.tavily_api_key.strip():
        return {
            "ok": False,
            "error": "Configure TAVILY_API_KEY para buscar lo que ve la cámara",
            "subject": subject,
            "code": "missing_tavily",
        }

    return {
        "ok": False,
        "error": f"No encontré información sobre {subject}",
        "subject": subject,
    }
