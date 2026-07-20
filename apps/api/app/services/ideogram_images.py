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
# Costos reales Ideogram 4.0 por imagen (API pricing). Al monedero CED se cobra
# $0.06 por unidad del recurso "image_text" (margen sobre Turbo $0.03).
IDEOGRAM_PROVIDER_COST_USD: dict[str, float] = {
    "FLASH": 0.03,  # reserved; FLASH aún no soportado en v4
    "TURBO": 0.03,
    "DEFAULT": 0.06,
    "QUALITY": 0.10,
}
IDEOGRAM_TURBO_COST_USD = IDEOGRAM_PROVIDER_COST_USD["TURBO"]
IDEOGRAM_WALLET_COST_USD = 0.06
_TIMEOUT_SEC = 45.0


def _friendly_ideogram_error(raw: str) -> str:
    msg = (raw or "").strip()
    return msg[:200] if msg else "No pude generar la imagen con Ideogram."


def _provider_cost_usd(rendering_speed: str) -> float:
    return IDEOGRAM_PROVIDER_COST_USD.get(rendering_speed.upper(), IDEOGRAM_TURBO_COST_USD)


def _build_form_files(
    *,
    prompt: str,
    rendering_speed: str,
    resolution: str,
    include_num_images: bool,
) -> dict[str, tuple[None, str]]:
    files: dict[str, tuple[None, str]] = {
        "text_prompt": (None, prompt[:2000]),
        "rendering_speed": (None, rendering_speed),
        "resolution": (None, resolution),
    }
    # v3 documenta num_images (default 1). v4 no lo lista en el schema, pero
    # pedirlo explícitamente evita el riesgo de un default >1 si Ideogram lo
    # acepta; si responde 400 por campo desconocido, reintentamos sin él.
    if include_num_images:
        files["num_images"] = (None, "1")
    return files


def generate_image_ideogram(*, prompt: str, quality: str = "text") -> dict[str, Any]:
    """Genera UNA imagen con Ideogram 4.0 Turbo. Mismo shape que generate_image_gemini.

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

    rendering_speed = (settings.ideogram_rendering_speed or "TURBO").strip().upper() or "TURBO"
    if rendering_speed not in IDEOGRAM_PROVIDER_COST_USD:
        logger.warning(
            "[IDEOGRAM:IMAGE] rendering_speed inválido=%r — forzando TURBO",
            rendering_speed,
        )
        rendering_speed = "TURBO"
    resolution = (settings.ideogram_resolution or "2048x2048").strip() or "2048x2048"

    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            response = client.post(
                IDEOGRAM_GENERATE_URL,
                headers={"Api-Key": api_key},
                # Ideogram exige Content-Type multipart/form-data (rechaza urlencoded
                # con 415). httpx solo codifica como multipart si los campos van en
                # `files=` — con tuplas (None, valor) quedan como campos de texto
                # normales, sin agregar ningún campo extra al cuerpo.
                files=_build_form_files(
                    prompt=topic,
                    rendering_speed=rendering_speed,
                    resolution=resolution,
                    include_num_images=True,
                ),
            )
            # Si v4 rechaza num_images, reintentar sin el campo (siempre pedimos 1
            # conceptualmente; el log de num_returned vigila el default real).
            if response.status_code == 400 and "num_images" in (response.text or "").lower():
                logger.info("[IDEOGRAM:IMAGE] num_images rechazado por API — reintento sin campo")
                response = client.post(
                    IDEOGRAM_GENERATE_URL,
                    headers={"Api-Key": api_key},
                    files=_build_form_files(
                        prompt=topic,
                        rendering_speed=rendering_speed,
                        resolution=resolution,
                        include_num_images=False,
                    ),
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
    num_returned = len(data) if isinstance(data, list) else 0
    if num_returned <= 0:
        return {"ok": False, "error": "Ideogram no devolvió imagen", "code": "ideogram_error"}
    if num_returned > 1:
        # Cobrarían N× el precio por imagen y nosotros solo mostramos la primera.
        logger.error(
            "[IDEOGRAM:IMAGE] API devolvió %s imágenes (esperado 1) speed=%s — "
            "solo se usa data[0]; revisar billing Ideogram",
            num_returned,
            rendering_speed,
        )

    entry = data[0]
    if not entry.get("is_image_safe", True):
        return {
            "ok": False,
            "error": "El pedido no pasó el filtro de seguridad de Ideogram.",
            "code": "ideogram_safety_block",
            "num_images_returned": num_returned,
        }

    image_url = str(entry.get("url") or "").strip()
    if not image_url:
        return {
            "ok": False,
            "error": "Ideogram no devolvió una URL de imagen",
            "code": "ideogram_error",
            "num_images_returned": num_returned,
        }

    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            download = client.get(image_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IDEOGRAM:IMAGE] download error: %s", exc)
        return {
            "ok": False,
            "error": "No pude descargar la imagen generada por Ideogram.",
            "code": "ideogram_download_error",
            "num_images_returned": num_returned,
        }

    if download.status_code >= 400 or not download.content:
        logger.warning("[IDEOGRAM:IMAGE] download http %s", download.status_code)
        return {
            "ok": False,
            "error": "No pude descargar la imagen generada por Ideogram.",
            "code": "ideogram_download_error",
            "num_images_returned": num_returned,
        }

    mime = (download.headers.get("content-type") or "image/png").split(";")[0].strip() or "image/png"
    provider_cost = _provider_cost_usd(rendering_speed)
    # Costo real estimado de esta petición en Ideogram (= N × precio del tier).
    provider_request_cost = round(provider_cost * num_returned, 4)
    logger.info(
        "[IDEOGRAM:IMAGE] ok bytes=%s speed=%s resolution=%s num_returned=%s "
        "provider_cost_per_image=%.4f provider_request_cost=%.4f",
        len(download.content),
        rendering_speed,
        resolution,
        num_returned,
        provider_cost,
        provider_request_cost,
    )
    return {
        "ok": True,
        "raw_bytes": download.content,
        "mime_type": mime,
        "model": f"ideogram-v4-{rendering_speed.lower()}",
        "quality": quality,
        "provider": "ideogram",
        "rendering_speed": rendering_speed,
        "num_images_returned": num_returned,
        "num_images_requested": 1,
        # Costo real del proveedor por la imagen que guardamos (1× tier).
        "estimated_cost_usd": provider_cost,
        # Costo real estimado de la petición completa (si N>1, Ideogram cobra N).
        "provider_request_cost_usd": provider_request_cost,
        # Precio interno CED al monedero cuando aplica (1 unidad image_text).
        "wallet_unit_cost_usd": IDEOGRAM_WALLET_COST_USD,
    }
