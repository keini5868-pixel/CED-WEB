"""Análisis de imágenes con Claude Vision — Modo Avanzado."""

from __future__ import annotations

import base64
import logging

import httpx

from app.services.advanced_mode.constants import ADVANCED_STREAM_MODEL, ADVANCED_VISION_PROMPT

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"},
)


def build_vision_prompt(user_text: str) -> str:
    cleaned = (user_text or "").strip()
    if cleaned and len(cleaned) > 3 and cleaned.lower() not in {
        "",
        "imagen adjunta",
        "📷 imagen adjunta",
        "analiza esta imagen",
        "analiza la imagen",
    }:
        return (
            f"{ADVANCED_VISION_PROMPT}\n\n"
            f"Pregunta del usuario: {cleaned}\n"
            "Responde de forma completa a esa petición."
        )
    return ADVANCED_VISION_PROMPT


def analyze_image_with_claude(
    *,
    api_key: str,
    image_bytes: bytes,
    media_type: str,
    user_text: str,
) -> str:
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Imagen demasiado grande. Máximo 5MB.")
    mime = media_type if media_type in ALLOWED_IMAGE_TYPES else "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = build_vision_prompt(user_text)
    payload = {
        "model": ADVANCED_STREAM_MODEL,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    with httpx.Client(timeout=90.0) as client:
        res = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        res.raise_for_status()
        data = res.json()
    blocks = data.get("content") or []
    reply = "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    if not reply:
        raise ValueError("Claude no devolvió análisis de la imagen.")
    return reply
