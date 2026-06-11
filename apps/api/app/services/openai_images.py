"""Generación de imágenes OpenAI GPT-Image-1 con límites por plan."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.domain.plans import get_plan_limits, normalize_plan_id
from app.services import supabase_db

logger = logging.getLogger(__name__)

IMAGE_API = "https://api.openai.com/v1/images/generations"
STD_COST_USD = 0.04
HD_COST_USD = 0.08


def _pick_quality(prompt: str, requested: str | None) -> str:
    if requested in ("standard", "hd"):
        return requested
    p = (prompt or "").lower()
    if any(k in p for k in ("logo", "4k", "ultra", "profesional", "detalle", "hd")):
        return "hd"
    return "standard"


def _month_image_counts(user_id: str) -> tuple[int, int]:
    try:
        return supabase_db.count_generated_images_this_month(user_id)
    except Exception:  # noqa: BLE001
        return 0, 0


def generate_image(
    *,
    user_id: str,
    plan_id: str | None,
    prompt: str,
    quality: str | None = "auto",
) -> dict[str, Any]:
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Prompt vacío"}
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY no configurada"}

    limits = get_plan_limits(normalize_plan_id(plan_id))
    std_used, hd_used = _month_image_counts(user_id)
    picked = _pick_quality(topic, None if quality == "auto" else quality)

    if picked == "hd":
        cap = limits.ai_images_hd_per_month
        used = hd_used
    else:
        cap = limits.ai_images_standard_per_month
        used = std_used

    if cap <= 0:
        return {"ok": False, "error": "Tu plan no incluye imágenes IA.", "code": "plan_limit"}
    if used >= cap:
        return {
            "ok": False,
            "error": f"Límite mensual de imágenes {picked} alcanzado.",
            "code": "quota_exhausted",
        }

    model = settings.openai_model_image.strip() or "gpt-image-1"
    payload: dict[str, Any] = {
        "model": model,
        "prompt": topic[:4000],
        "size": "1024x1024",
        "quality": "high" if picked == "hd" else "medium",
        "n": 1,
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            res = client.post(
                IMAGE_API,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if res.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"OpenAI rechazó la imagen ({res.status_code})",
                }
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[OPENAI:IMAGE] failed")
        return {"ok": False, "error": str(exc)}

    items = data.get("data") or []
    if not items:
        return {"ok": False, "error": "Sin imagen en respuesta"}

    url = items[0].get("url") or ""
    b64 = items[0].get("b64_json")
    public_url = url
    if not public_url and b64:
        from app.services.publish_media import decode_image_data, store_publish_image

        data_url = f"data:image/png;base64,{b64}"
        raw, mime = decode_image_data(data_url)
        public_url = store_publish_image(user_id, raw, mime)
    elif public_url.startswith("data:"):
        from app.services.publish_media import decode_image_data, store_publish_image

        raw, mime = decode_image_data(public_url)
        public_url = store_publish_image(user_id, raw, mime)

    cost = HD_COST_USD if picked == "hd" else STD_COST_USD
    try:
        supabase_db.insert_generated_image(
            user_id=user_id,
            prompt=topic,
            quality=picked,
            model=model,
            public_url=public_url,
            estimated_cost_usd=cost,
        )
    except Exception:  # noqa: BLE001
        logger.warning("[OPENAI:IMAGE] log insert failed")

    return {
        "ok": True,
        "url": public_url,
        "quality": picked,
        "model": model,
        "estimated_cost_usd": cost,
    }
