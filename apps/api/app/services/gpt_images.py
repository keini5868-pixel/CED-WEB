"""GPT Image (OpenAI) — motor de tipografía legible para pedidos con texto explícito.

Default de escena sigue siendo Nano Banana 2 (Gemini). Este módulo solo se usa
cuando `prompt_requires_precise_text` / `prefer_ideogram` marca el pedido.
Calidad fija en `medium` (~$0.034 en gpt-image-1.5) para caber en el cargo
`image_text` del monedero ($0.06) con margen; high (~$0.13) no se usa aquí.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

IMAGE_GENERATIONS_API = "https://api.openai.com/v1/images/generations"
IMAGE_EDITS_API = "https://api.openai.com/v1/images/edits"

# COGS aproximado OpenAI (1024×1024 medium) — gpt-image-1.5.
GPT_IMAGE_MEDIUM_COST_USD = 0.034
GPT_IMAGE_HIGH_COST_USD = 0.133
# Timeout: más lento que Ideogram Turbo; no bloquear el turno eternamente.
_TIMEOUT_SEC = 50.0


def _parse_openai_error(res: httpx.Response) -> str:
    try:
        body = res.json()
        err = body.get("error") or {}
        if isinstance(err, dict):
            msg = str(err.get("message") or "").strip()
            if msg:
                return msg[:200]
    except Exception:  # noqa: BLE001
        pass
    return (res.text or "")[:200].strip() or f"HTTP {res.status_code}"


def _extract_b64(data: dict[str, Any]) -> str | None:
    items = data.get("data") or []
    if not items or not isinstance(items[0], dict):
        return None
    b64 = items[0].get("b64_json")
    if isinstance(b64, str) and b64.strip():
        return b64.strip()
    return None


def generate_image_gpt(
    *,
    prompt: str,
    quality: str = "medium",
) -> dict[str, Any]:
    """Genera UNA imagen con GPT Image. Shape compatible con Ideogram/Gemini routers.

    quality: solo ``medium`` (default) o ``high``. Para tipografía usamos medium.
    """
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    model = (settings.openai_model_image or "gpt-image-1.5").strip() or "gpt-image-1.5"
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Prompt vacío", "code": "empty_prompt"}
    from app.services.copy_quality import ensure_image_quality_guards

    topic = ensure_image_quality_guards(topic, wants_text=True)
    if not api_key:
        return {
            "ok": False,
            "error": "OPENAI_API_KEY no configurada",
            "code": "config_error",
        }

    # Forzar medium salvo HD explícito — high rompe el margen del monedero image_text.
    q = "high" if (quality or "").strip().lower() in ("hd", "high") else "medium"
    cost = GPT_IMAGE_HIGH_COST_USD if q == "high" else GPT_IMAGE_MEDIUM_COST_USD

    payload: dict[str, Any] = {
        "model": model,
        "prompt": topic[:4000],
        "size": "1024x1024",
        "quality": q,
        "n": 1,
    }
    # gpt-image-* suele devolver b64; dall-e-3 pide response_format.
    if model.lower().startswith("dall-e"):
        payload["response_format"] = "b64_json"

    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            res = client.post(
                IMAGE_GENERATIONS_API,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException:
        logger.warning("[GPT-IMAGE] timeout model=%s", model)
        return {
            "ok": False,
            "error": "GPT Image no respondió a tiempo.",
            "code": "gpt_image_timeout",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GPT-IMAGE] request error: %s", exc)
        return {
            "ok": False,
            "error": "No pude contactar GPT Image.",
            "code": "gpt_image_error",
        }

    if res.status_code >= 400:
        detail = _parse_openai_error(res)
        logger.error("[GPT-IMAGE] %s model=%s %s", res.status_code, model, detail)
        return {
            "ok": False,
            "error": detail or "Error de GPT Image.",
            "code": "gpt_image_http",
        }

    try:
        body = res.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"Respuesta inválida de GPT Image: {exc}",
            "code": "gpt_image_parse",
        }

    b64 = _extract_b64(body)
    if not b64:
        return {
            "ok": False,
            "error": "GPT Image no devolvió imagen.",
            "code": "gpt_image_empty",
        }

    try:
        raw = base64.b64decode(b64)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"No pude decodificar la imagen: {exc}",
            "code": "gpt_image_decode",
        }

    if len(raw) < 512:
        return {
            "ok": False,
            "error": "Imagen GPT demasiado pequeña.",
            "code": "gpt_image_empty",
        }

    logger.info(
        "[GPT-IMAGE] ok model=%s quality=%s bytes=%s cost≈%.3f",
        model,
        q,
        len(raw),
        cost,
    )
    return {
        "ok": True,
        "raw_bytes": raw,
        "mime_type": "image/png",
        "model": model,
        "quality": "text",
        "provider": "gpt_image",
        "estimated_cost_usd": cost,
        "provider_request_cost_usd": cost,
    }


def edit_image_gpt(
    *,
    prompt: str,
    image_bytes: bytes,
    content_type: str = "image/png",
    quality: str = "medium",
) -> dict[str, Any]:
    """Edita UNA imagen existente con GPT Image (/v1/images/edits).

    Caso clave: conservar sujeto/fondo y agregar tipografía persuasiva legible.
    """
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    model = (settings.openai_model_image or "gpt-image-1.5").strip() or "gpt-image-1.5"
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Prompt vacío", "code": "empty_prompt"}
    from app.services.copy_quality import ensure_image_quality_guards

    topic = ensure_image_quality_guards(topic, wants_text=True)
    if not api_key:
        return {
            "ok": False,
            "error": "OPENAI_API_KEY no configurada",
            "code": "config_error",
        }
    if not image_bytes or len(image_bytes) < 512:
        return {
            "ok": False,
            "error": "Imagen de referencia inválida",
            "code": "invalid_image",
        }

    q = "high" if (quality or "").strip().lower() in ("hd", "high") else "medium"
    cost = GPT_IMAGE_HIGH_COST_USD if q == "high" else GPT_IMAGE_MEDIUM_COST_USD
    mime = (content_type or "image/png").split(";")[0].strip().lower()
    if mime not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        mime = "image/png"
    ext = "jpg" if mime in ("image/jpeg", "image/jpg") else ("webp" if mime == "image/webp" else "png")
    filename = f"reference.{ext}"

    data = {
        "model": model,
        "prompt": topic[:4000],
        "size": "1024x1024",
        "quality": q,
        "n": "1",
        "input_fidelity": "high",
    }
    files = {"image": (filename, image_bytes, mime)}

    try:
        with httpx.Client(timeout=_TIMEOUT_SEC) as client:
            res = client.post(
                IMAGE_EDITS_API,
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files=files,
            )
    except httpx.TimeoutException:
        logger.warning("[GPT-IMAGE:EDIT] timeout model=%s", model)
        return {
            "ok": False,
            "error": "GPT Image edit no respondió a tiempo.",
            "code": "gpt_image_timeout",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GPT-IMAGE:EDIT] request error: %s", exc)
        return {
            "ok": False,
            "error": "No pude contactar GPT Image (edit).",
            "code": "gpt_image_error",
        }

    if res.status_code >= 400:
        detail = _parse_openai_error(res)
        logger.error("[GPT-IMAGE:EDIT] %s model=%s %s", res.status_code, model, detail)
        return {
            "ok": False,
            "error": detail or "Error de GPT Image edit.",
            "code": "gpt_image_http",
        }

    try:
        body = res.json()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"Respuesta inválida de GPT Image edit: {exc}",
            "code": "gpt_image_parse",
        }

    b64 = _extract_b64(body)
    if not b64:
        return {
            "ok": False,
            "error": "GPT Image edit no devolvió imagen.",
            "code": "gpt_image_empty",
        }

    try:
        raw = base64.b64decode(b64)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"No pude decodificar la imagen editada: {exc}",
            "code": "gpt_image_decode",
        }

    if len(raw) < 512:
        return {
            "ok": False,
            "error": "Imagen GPT edit demasiado pequeña.",
            "code": "gpt_image_empty",
        }

    logger.info(
        "[GPT-IMAGE:EDIT] ok model=%s quality=%s bytes=%s cost≈%.3f",
        model,
        q,
        len(raw),
        cost,
    )
    return {
        "ok": True,
        "raw_bytes": raw,
        "mime_type": "image/png",
        "model": model,
        "quality": "text",
        "provider": "gpt_image_edit",
        "estimated_cost_usd": cost,
        "provider_request_cost_usd": cost,
        "used_reference": True,
    }
