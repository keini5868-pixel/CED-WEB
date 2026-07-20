"""Generación de imágenes vía Ideogram 4.0 (IDEOGRAM_API_KEY) — texto legible en la imagen.

Opción ALTERNATIVA a Gemini (ver `gemini_images.py`), no un reemplazo. Solo se invoca
desde `gemini_images.generate_image()` cuando el pedido exige texto literal explícito
(ver `copy_quality.prompt_requires_ideogram_text`) y el plan/monedero del usuario lo
permite. Ante cualquier falla, el llamador degrada a Gemini con un aviso honesto.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

IDEOGRAM_GENERATE_URL = "https://api.ideogram.ai/v1/ideogram-v4/generate"
# $0.03 costo real (tier TURBO) — se cobra $0.06 al monedero (recurso "image_text"),
# margen igual al resto de recursos de recarga (aprobado Keini 2026-07).
IDEOGRAM_TURBO_COST_USD = 0.03
_TIMEOUT_SEC = 45.0


def _friendly_ideogram_error(raw: str) -> str:
    msg = (raw or "").strip()
    return msg[:200] if msg else "No pude generar la imagen con Ideogram."


def generate_image_ideogram(*, prompt: str, quality: str = "text") -> dict[str, Any]:
    """Genera imagen con Ideogram 4.0 Turbo. Mismo shape de retorno que generate_image_gemini.

    Retorna {"ok": False, ...} ante cualquier problema (config, red, safety, timeout) —
    el llamador SIEMPRE debe poder degradar a Gemini sin propagar la falla al usuario.
    """
    settings = get_settings()
    api_key = settings.ideogram_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Prompt vacío", "code": "empty_prompt"}
    if not api_key:
        return {"ok": False, "error": "IDEOGRAM_API_KEY no configurada", "code": "config_error"}

    rendering_speed = (settings.ideogram_rendering_speed or "TURBO").strip().upper()
    resolution = (settings.ideogram_resolution or "2048x2048").strip()

    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            response = client.post(
                IDEOGRAM_GENERATE_URL,
                headers={"Api-Key": api_key},
                data={
                    "text_prompt": topic[:2000],
                    "rendering_speed": rendering_speed,
                    "resolution": resolution,
                },
            )
    except httpx.TimeoutException:
        logger.warning("[IDEOGRAM:IMAGE] timeout on generate")
        return {"ok": False, "error": "Ideogram no respondió a tiempo.", "code": "ideogram_timeout"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IDEOGRAM:IMAGE] request error: %s", exc)
        return {"ok": False, "error": _friendly_ideogram_error(str(exc)), "code": "ideogram_error"}

    if response.status_code >= 400:
        detail = response.text[:200]
        logger.warning("[IDEOGRAM:IMAGE] http %s: %s", response.status_code, detail)
        code = "ideogram_safety_block" if response.status_code == 422 else "ideogram_error"
        return {"ok": False, "error": _friendly_ideogram_error(detail), "code": code}

    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IDEOGRAM:IMAGE] bad json response: %s", exc)
        return {"ok": False, "error": "Ideogram devolvió una respuesta inválida.", "code": "ideogram_error"}

    data = payload.get("data") or []
    if not data:
        return {"ok": False, "error": "Ideogram no devolvió imagen", "code": "ideogram_error"}

    entry = data[0]
    if not entry.get("is_image_safe", True):
        return {
            "ok": False,
            "error": "El pedido no pasó el filtro de seguridad de Ideogram.",
            "code": "ideogram_safety_block",
        }

    image_url = str(entry.get("url") or "").strip()
    if not image_url:
        return {"ok": False, "error": "Ideogram no devolvió una URL de imagen", "code": "ideogram_error"}

    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            download = client.get(image_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IDEOGRAM:IMAGE] download error: %s", exc)
        return {
            "ok": False,
            "error": "No pude descargar la imagen generada por Ideogram.",
            "code": "ideogram_download_error",
        }

    if download.status_code >= 400 or not download.content:
        logger.warning("[IDEOGRAM:IMAGE] download http %s", download.status_code)
        return {
            "ok": False,
            "error": "No pude descargar la imagen generada por Ideogram.",
            "code": "ideogram_download_error",
        }

    mime = (download.headers.get("content-type") or "image/png").split(";")[0].strip() or "image/png"
    logger.info(
        "[IDEOGRAM:IMAGE] ok bytes=%s speed=%s resolution=%s",
        len(download.content),
        rendering_speed,
        resolution,
    )
    return {
        "ok": True,
        "raw_bytes": download.content,
        "mime_type": mime,
        "model": "ideogram-v4-turbo",
        "quality": quality,
        "provider": "ideogram",
        "estimated_cost_usd": IDEOGRAM_TURBO_COST_USD,
    }
