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


def _reference_prompt(user_prompt: str, style_mode: str) -> str:
    topic = (user_prompt or "").strip() or "Genera una nueva versión de la imagen de referencia."
    if style_mode == "inspired":
        return (
            "Usa la imagen adjunta como inspiración de estilo, paleta y composición. "
            f"Genera una imagen nueva que cumpla: {topic}. "
            "Mantén la esencia visual pero adapta al pedido."
        )
    if style_mode == "variation":
        return (
            f"Genera una variación de la imagen adjunta: {topic}. "
            "Conserva elementos clave (estilo, tonos, composición) con cambios según las instrucciones."
        )
    if style_mode == "edit":
        return (
            f"Edita la imagen adjunta: {topic}. "
            "Mantén intacto todo lo que no se pide cambiar explícitamente."
        )
    return topic


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


def generate_image_with_reference_gemini(
    *,
    prompt: str,
    reference_image: bytes,
    content_type: str = "image/jpeg",
    style_mode: str = "inspired",
    quality: str = "standard",
) -> dict[str, Any]:
    """Variación / inspiración / edición con imagen de referencia vía Gemini."""
    from google import genai
    from google.genai import types

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Indica qué quieres generar o cambiar", "code": "empty_prompt"}
    if not api_key:
        return {"ok": False, "error": "GOOGLE_API_KEY no configurada", "code": "config_error"}
    if not reference_image:
        return {"ok": False, "error": "Imagen de referencia vacía", "code": "invalid_image"}

    mode = style_mode if style_mode in ("inspired", "variation", "edit") else "inspired"
    mime = (content_type or "image/jpeg").split(";")[0].strip().lower()
    if mime not in ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"):
        mime = "image/jpeg"

    enriched = _reference_prompt(topic, mode)
    client = genai.Client(api_key=api_key)
    last_error = "No pude generar la imagen con referencia en Gemini."

    for model in _image_models():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=reference_image, mime_type=mime),
                            types.Part.from_text(text=enriched[:4000]),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    temperature=0.85,
                ),
            )
            payload = _extract_image_payload(response)
            if payload:
                raw, out_mime = payload
                logger.info("[GEMINI:REF-IMG] ok model=%s mode=%s bytes=%s", model, mode, len(raw))
                return {
                    "ok": True,
                    "raw_bytes": raw,
                    "mime_type": out_mime,
                    "model": model,
                    "quality": quality,
                    "style_mode": mode,
                    "provider": "gemini",
                    "estimated_cost_usd": (
                        GEMINI_HD_COST_USD if quality == "hd" else GEMINI_STD_COST_USD
                    ),
                }
            last_error = f"Gemini ({model}) no devolvió imagen con referencia"
            logger.warning("[GEMINI:REF-IMG] empty model=%s mode=%s", model, mode)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:200]
            logger.warning("[GEMINI:REF-IMG] model=%s error: %s", model, last_error)

    return {"ok": False, "error": last_error, "code": "gemini_error"}
