"""Generación de imágenes OpenAI GPT-Image-1 con límites por plan."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.deps.auth import is_super_admin
from app.deps.plan_access import effective_plan_limits
from app.domain.plans import PlanId, get_plan_limits
from app.services import supabase_db

logger = logging.getLogger(__name__)

IMAGE_API = "https://api.openai.com/v1/images/generations"
STD_COST_USD = 0.04
HD_COST_USD = 0.08


def _pick_quality(prompt: str, requested: str | None) -> str:
    if requested in ("standard", "hd", "low", "medium", "high"):
        if requested in ("hd", "high"):
            return "hd"
        if requested in ("low", "medium", "standard"):
            return "standard"
    p = (prompt or "").lower()
    if any(k in p for k in ("logo", "4k", "ultra", "profesional", "detalle", "hd")):
        return "hd"
    return "standard"


def _build_image_payload(model: str, topic: str, picked: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": topic[:4000],
        "n": 1,
    }
    if model.startswith("gpt-image"):
        payload["size"] = "1024x1024"
        payload["quality"] = "high" if picked == "hd" else "medium"
        return payload
    if model == "dall-e-3":
        payload["size"] = "1024x1024"
        payload["quality"] = "hd" if picked == "hd" else "standard"
        payload["response_format"] = "b64_json"
        return payload
    payload["size"] = "1024x1024"
    payload["response_format"] = "b64_json"
    return payload


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
    return res.text[:200].strip() or f"HTTP {res.status_code}"


def _request_openai_image(
    *,
    api_key: str,
    model: str,
    topic: str,
    picked: str,
) -> tuple[dict[str, Any] | None, str | None]:
    payload = _build_image_payload(model, topic, picked)
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
            detail = _parse_openai_error(res)
            logger.error("[OPENAI:IMAGE] %s model=%s %s", res.status_code, model, detail)
            return None, detail
        return res.json(), None


def _day_image_counts(user_id: str) -> tuple[int, int]:
    try:
        return supabase_db.count_generated_images_today(user_id)
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

    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        limits = get_plan_limits(PlanId.FOUNDING.value)
    else:
        limits, _reason, _trial = effective_plan_limits(user_id)

    std_used, hd_used = _day_image_counts(user_id)
    picked = _pick_quality(topic, None if quality == "auto" else quality)

    if picked == "hd":
        cap = limits.ai_images_hd_per_day
        used = hd_used
    else:
        cap = limits.ai_images_standard_per_day
        used = std_used

    if cap <= 0:
        return {
            "ok": False,
            "error": "Tu plan actual no incluye generación de imágenes. Mejora tu plan en Precios.",
            "code": "plan_limit",
        }
    if used >= cap:
        return {
            "ok": False,
            "error": f"Límite diario de imágenes {picked} alcanzado ({cap}/día). Mañana se reinicia tu cupo.",
            "code": "quota_exhausted",
        }

    primary = settings.openai_model_image.strip() or "gpt-image-1"
    models_to_try = [primary]
    if primary.startswith("gpt-image") and "dall-e-3" not in models_to_try:
        models_to_try.append("dall-e-3")

    data: dict[str, Any] | None = None
    model = primary
    last_error = "No pude generar la imagen."
    try:
        for candidate in models_to_try:
            model = candidate
            data, err = _request_openai_image(
                api_key=api_key,
                model=candidate,
                topic=topic,
                picked=picked,
            )
            if data is not None:
                break
            last_error = err or last_error
    except Exception as exc:  # noqa: BLE001
        logger.exception("[OPENAI:IMAGE] failed")
        return {"ok": False, "error": str(exc)}

    if data is None:
        return {
            "ok": False,
            "error": f"No pude generar la imagen: {last_error}",
            "code": "openai_error",
        }

    items = data.get("data") or []
    if not items:
        return {"ok": False, "error": "Sin imagen en respuesta"}

    url = items[0].get("url") or ""
    b64 = items[0].get("b64_json")
    public_url = url
    if not public_url and not b64:
        return {"ok": False, "error": "OpenAI no devolvió imagen usable", "code": "openai_error"}

    if not public_url and b64:
        from app.services.publish_media import decode_image_data, store_publish_image_for_client

        data_url = f"data:image/png;base64,{b64}"
        raw, mime = decode_image_data(data_url)
        public_url = store_publish_image_for_client(user_id, raw, mime)
    elif public_url.startswith("data:"):
        from app.services.publish_media import decode_image_data, store_publish_image_for_client

        raw, mime = decode_image_data(public_url)
        public_url = store_publish_image_for_client(user_id, raw, mime)
    elif public_url.startswith("http"):
        from app.services.publish_media import decode_image_data, store_publish_image_for_client

        try:
            raw, mime = decode_image_data(public_url)
            public_url = store_publish_image_for_client(user_id, raw, mime)
        except Exception:  # noqa: BLE001
            pass

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
