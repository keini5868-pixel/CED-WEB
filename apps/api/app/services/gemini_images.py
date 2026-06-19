"""Generación de imágenes vía Gemini (GOOGLE_API_KEY) — alternativa sin OpenAI."""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_IMAGE_MODELS = (
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation",
)
GEMINI_STD_COST_USD = 0.01
GEMINI_HD_COST_USD = 0.02


def _image_models() -> tuple[str, ...]:
    settings = get_settings()
    primary = settings.gemini_image_model.strip()
    if primary:
        return (primary, *(m for m in DEFAULT_GEMINI_IMAGE_MODELS if m != primary))
    return DEFAULT_GEMINI_IMAGE_MODELS


def _extract_image_payload(response: Any) -> tuple[bytes, str] | None:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if not inline:
            continue
        raw = getattr(inline, "data", None)
        if not raw:
            continue
        mime = getattr(inline, "mime_type", None) or "image/png"
        if isinstance(raw, str):
            return base64.b64decode(raw), mime
        return bytes(raw), mime
    return None


def generate_image_gemini(
    *,
    prompt: str,
    quality: str = "standard",
) -> dict[str, Any]:
    """Genera imagen con Gemini. Requiere GOOGLE_API_KEY."""
    from google import genai
    from google.genai import types

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Prompt vacío"}
    if not api_key:
        return {"ok": False, "error": "GOOGLE_API_KEY no configurada", "code": "config_error"}

    client = genai.Client(api_key=api_key)
    last_error = "No pude generar la imagen con Gemini."

    for model in _image_models():
        try:
            response = client.models.generate_content(
                model=model,
                contents=topic[:4000],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    temperature=0.9,
                ),
            )
            payload = _extract_image_payload(response)
            if payload:
                raw, mime = payload
                logger.info("[GEMINI:IMAGE] ok model=%s bytes=%s", model, len(raw))
                return {
                    "ok": True,
                    "raw_bytes": raw,
                    "mime_type": mime,
                    "model": model,
                    "quality": quality,
                    "provider": "gemini",
                    "estimated_cost_usd": (
                        GEMINI_HD_COST_USD if quality == "hd" else GEMINI_STD_COST_USD
                    ),
                }
            last_error = f"Gemini ({model}) no devolvió imagen usable"
            logger.warning("[GEMINI:IMAGE] empty model=%s", model)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:200]
            logger.warning("[GEMINI:IMAGE] model=%s error: %s", model, last_error)

    return {"ok": False, "error": last_error, "code": "gemini_error"}
