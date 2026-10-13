"""Centinela — QA visual post-generación (Gemini Flash, una pasada)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("ced.sentinel.vision")

_VISION_MODEL = "gemini-2.5-flash"
_MAX_ISSUES = 4


def should_vision_audit_request(user_text: str) -> bool:
    """Solo auditar cuando hay restricciones visuales o copy literal en la pieza."""
    from app.services.copy_quality import (
        extract_image_visual_constraints,
        extract_literal_on_image_copy,
        user_asks_for_on_image_copy,
    )

    t = (user_text or "").strip()
    if not t:
        return False
    if extract_image_visual_constraints(t):
        return True
    if extract_literal_on_image_copy(t) or user_asks_for_on_image_copy(t):
        return True
    return bool(re.search(r"(?i)\bfondo\b", t) and re.search(r"(?i)(?:letras?|texto|frase)", t))


def _constraints_for_prompt(user_text: str) -> list[str]:
    from app.services.copy_quality import (
        extract_image_visual_constraints,
        extract_literal_on_image_copy,
    )

    labels: list[str] = []
    key_labels = {
        "dark_background": "Fondo oscuro o negro (no blanco dominante).",
        "light_background": "Fondo claro/blanco como pidió el usuario.",
        "white_text": "Relleno de letras blanco.",
        "cyan_outline": "Borde/contorno cian claro (NO morado/lavanda).",
    }
    for key in extract_image_visual_constraints(user_text):
        labels.append(key_labels.get(key, key))
    for quote in extract_literal_on_image_copy(user_text):
        q = quote.strip()
        if q:
            labels.append(f'Texto visible exacto: «{q}».')
    return labels


def _parse_audit_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _gemini_audit(image_bytes: bytes, mime: str, prompt: str) -> dict[str, Any]:
    from app.config import get_settings

    api_key = get_settings().google_api_key.strip()
    if not api_key:
        return {}
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=_VISION_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type=mime if mime.startswith("image/") else "image/png",
                        ),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=384,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                content = getattr(candidates[0], "content", None)
                parts = getattr(content, "parts", None) or []
                text = " ".join(
                    str(getattr(p, "text", "") or "") for p in parts
                ).strip()
        return _parse_audit_json(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SENTINEL:VISION] gemini audit failed: %s", exc)
        return {}


def audit_generated_image_against_request(
    image_url: str,
    user_text: str,
) -> tuple[bool, str]:
    """
    Devuelve (needs_correction, detail).
    Si no puede auditar (sin key, descarga fallida), needs_correction=False.
    """
    if not should_vision_audit_request(user_text):
        return False, ""

    constraints = _constraints_for_prompt(user_text)
    if not constraints:
        return False, ""

    try:
        from app.services.publish_media import decode_image_data

        image_bytes, mime = decode_image_data(image_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SENTINEL:VISION] skip download url=%s err=%s", (image_url or "")[:80], exc)
        return False, ""

    req = (user_text or "").strip()[:1200]
    bullet = "\n".join(f"- {c}" for c in constraints[:8])
    prompt = (
        "Eres QA de imágenes generadas para CED. Mira la imagen y el pedido.\n"
        "Responde SOLO JSON válido (sin markdown).\n\n"
        f"Pedido del usuario:\n{req}\n\n"
        f"Comprueba:\n{bullet}\n\n"
        'Formato: {"pass": true|false, "issues": ["motivo breve en español"], '
        '"dominant_background": "dark|light|mixed", '
        '"text_outline_color": "cyan|purple|white|other|none", '
        '"visible_text": "texto que se lee en la imagen"}\n'
        "pass=false si viola cualquier punto del pedido (fondo, color de borde, texto)."
    )

    data = _gemini_audit(image_bytes, mime, prompt)
    if not data:
        return False, ""

    passed = data.get("pass")
    if passed is True:
        return False, ""

    issues = data.get("issues")
    if isinstance(issues, list):
        parts = [str(x).strip() for x in issues if str(x).strip()][: _MAX_ISSUES]
    else:
        parts = []
    if not parts:
        from app.services.copy_quality import extract_image_visual_constraints

        keys = extract_image_visual_constraints(user_text)
        bg = str(data.get("dominant_background") or "").lower()
        outline = str(data.get("text_outline_color") or "").lower()
        if outline == "purple" and "cyan_outline" in keys:
            parts.append("El borde se ve morado; el usuario pidió cian.")
        elif bg == "light" and "dark_background" in keys:
            parts.append("El fondo se ve claro; el usuario pidió fondo oscuro.")
        else:
            parts.append("La imagen no coincide con el pedido visual.")

    detail = "; ".join(parts)[:500]
    logger.info(
        "[SENTINEL:VISION] fail issues=%s visible=%r",
        detail[:120],
        str(data.get("visible_text") or "")[:80],
    )
    return True, detail


def vision_retry_brief_suffix(detail: str) -> str:
    clean = " ".join((detail or "").split())[:400]
    if not clean:
        return (
            "La imagen anterior no cumplió el pedido. "
            "Regenera cumpliendo fondo, colores de texto y frase exacta."
        )
    return (
        f"QA visual: la imagen anterior falló porque: {clean}. "
        "Corrige SOLO eso en esta generación."
    )
