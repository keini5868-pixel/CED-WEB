"""Extracción de descripción de oferta — texto o imagen (visión one-shot, sin sesión)."""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

VISION_MODEL = "gemini-2.5-flash"

PRODUCT_VISION_PROMPT = (
    "Describe el producto o servicio mostrado en esta imagen/flyer para un estudio "
    "de viabilidad de mercado. En español, 3-6 oraciones. Incluye: qué se ofrece, "
    "público aparente, precio o texto de oferta si es legible, diferenciadores visibles. "
    "Si es un flyer, resume el mensaje de venta. NO inventes marcas ni precios que no "
    "se lean claramente. Si no hay precio visible, dilo."
)


def _decode_image(image_b64: str) -> bytes:
    raw = (image_b64 or "").strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def describe_offering_from_image(image_b64: str) -> str:
    """Visión aislada — no registra contexto de publicación ni chat."""
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return ""
    try:
        image_bytes = _decode_image(image_b64)
    except Exception:  # noqa: BLE001
        logger.warning("[VIABILITY-PILOT] invalid image b64")
        return ""
    if len(image_bytes) < 80:
        return ""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        mime = "image/jpeg"
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif image_bytes[:4] == b"RIFF":
            mime = "image/webp"

        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime),
                        types.Part.from_text(text=PRODUCT_VISION_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        return text[:1200]
    except Exception:  # noqa: BLE001
        logger.exception("[VIABILITY-PILOT] vision failed")
        return ""


def resolve_offering_text(
    *,
    description: str | None,
    image_b64: str | None,
) -> dict[str, Any]:
    text = (description or "").strip()
    image_desc = ""
    if image_b64 and image_b64.strip():
        image_desc = describe_offering_from_image(image_b64)

    parts = [p for p in (text, image_desc) if p]
    combined = "\n\n".join(parts).strip()
    return {
        "offering": combined,
        "text_input": text,
        "image_description": image_desc,
        "has_image": bool(image_desc),
    }
