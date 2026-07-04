"""Generación de imágenes basadas en referencia visual — GPT-Image-1 + fallback DALL-E 3."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.deps.auth import is_super_admin
from app.deps.plan_access import effective_plan_limits
from app.domain.plans import PlanId, get_plan_limits
from app.services import supabase_db
from app.services.gemini_images import GEMINI_HD_COST_USD, GEMINI_STD_COST_USD, _day_image_counts

logger = logging.getLogger(__name__)

IMAGE_EDITS_API = "https://api.openai.com/v1/images/edits"
IMAGE_GENERATIONS_API = "https://api.openai.com/v1/images/generations"
CHAT_COMPLETIONS_API = "https://api.openai.com/v1/chat/completions"

ALLOWED_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"})
MAX_REFERENCE_BYTES = 5 * 1024 * 1024

# Caché de análisis de estilo por hash de imagen (evita re-analizar en variaciones seguidas)
_style_cache: dict[str, str] = {}
_STYLE_CACHE_MAX = 64

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def build_reference_prompt(user_prompt: str, style_mode: str) -> str:
    """Enriquece el prompt según el modo de referencia."""
    topic = (user_prompt or "").strip() or "Genera una nueva versión de la imagen de referencia."
    if style_mode == "inspired":
        return (
            "Basándote en el estilo, paleta de colores y composición de la imagen de referencia "
            f"proporcionada, genera una nueva imagen que cumpla con: {topic}. "
            "Mantén la esencia visual de la referencia pero adapta al pedido."
        )
    if style_mode == "variation":
        return (
            f"Genera una variación de la imagen de referencia que: {topic}. "
            "Mantén elementos clave de la referencia (composición, estilo, tonos) "
            "pero crea una versión distinta según las instrucciones."
        )
    if style_mode == "edit":
        return (
            f"Edita la imagen de referencia: {topic}. "
            "Mantén intacto todo lo que no se menciona explícitamente."
        )
    return topic


def _image_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:32]


def _cache_style_description(image_hash: str, description: str) -> None:
    if len(_style_cache) >= _STYLE_CACHE_MAX:
        oldest = next(iter(_style_cache))
        _style_cache.pop(oldest, None)
    _style_cache[image_hash] = description


def _pick_quality(requested: str | None, *, plan_allows_hd: bool) -> str:
    if requested == "hd" and plan_allows_hd:
        return "hd"
    return "standard"


def _check_image_quota(user_id: str, quality: str) -> dict[str, Any] | None:
    """Devuelve dict de error si no puede generar; None si OK."""
    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        limits = get_plan_limits(PlanId.FOUNDING.value)
    else:
        limits, reason, _trial = effective_plan_limits(user_id)
        if reason == "trial_expired":
            limits = get_plan_limits(PlanId.FREE_BASIC.value)

    std_used, hd_used = _day_image_counts(user_id)
    if quality == "hd":
        cap = limits.ai_images_hd_per_day
        used = hd_used
    else:
        cap = limits.ai_images_standard_per_day
        used = std_used

    if cap <= 0:
        return {
            "ok": False,
            "error": "Generación con referencias requiere plan Starter o superior. Mejora tu plan en Precios.",
            "code": "plan_limit",
        }
    if used >= cap:
        return {
            "ok": False,
            "error": f"Límite diario de imágenes {quality} alcanzado ({cap}/día).",
            "code": "quota_exhausted",
        }
    return None


def _gpt_image_quality_param(picked: str) -> str:
    return "high" if picked == "hd" else "medium"


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


def _request_gpt_image_edit(
    *,
    api_key: str,
    model: str,
    prompt: str,
    reference_image: bytes,
    mime: str,
    style_mode: str,
    quality: str,
) -> tuple[dict[str, Any] | None, str | None]:
    ext = _EXT_BY_MIME.get(mime.lower(), "png")
    enriched = build_reference_prompt(prompt, style_mode)
    picked = quality
    data: dict[str, str] = {
        "model": model,
        "prompt": enriched[:4000],
        "size": "1024x1024",
        "quality": _gpt_image_quality_param(picked),
        "n": "1",
    }
    if style_mode == "variation":
        data["input_fidelity"] = "high"
    elif style_mode == "inspired":
        data["input_fidelity"] = "low"
    elif style_mode == "edit":
        data["input_fidelity"] = "high"

    files = [("image[]", (f"reference.{ext}", reference_image, mime))]

    with httpx.Client(timeout=120.0) as client:
        res = client.post(
            IMAGE_EDITS_API,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
        )
        if res.status_code >= 400:
            detail = _parse_openai_error(res)
            logger.error("[OPENAI:REF-IMG] edits %s model=%s %s", res.status_code, model, detail)
            return None, detail
        return res.json(), None


def _analyze_reference_style(
    *,
    api_key: str,
    reference_image: bytes,
    mime: str,
    image_hash: str,
) -> tuple[str | None, str | None]:
    cached = _style_cache.get(image_hash)
    if cached:
        return cached, None

    b64 = base64.b64encode(reference_image).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe en detalle esta imagen para usarla como referencia visual. "
                            "Incluye: estilo visual, paleta de colores, composición, mood, "
                            "elementos visuales clave y técnica artística."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 500,
    }
    with httpx.Client(timeout=60.0) as client:
        res = client.post(
            CHAT_COMPLETIONS_API,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if res.status_code >= 400:
            return None, _parse_openai_error(res)
        body = res.json()
    choices = body.get("choices") or []
    if not choices:
        return None, "Sin análisis de referencia"
    content = choices[0].get("message", {}).get("content", "")
    description = str(content).strip()
    if description:
        _cache_style_description(image_hash, description)
    return description or None, None


def _request_dalle_fallback(
    *,
    api_key: str,
    prompt: str,
    style_description: str,
    quality: str,
) -> tuple[dict[str, Any] | None, str | None]:
    combined = (
        f"{prompt.strip()}\n\nEstilo de referencia a seguir:\n{style_description}"
    )[:4000]
    payload = {
        "model": "dall-e-3",
        "prompt": combined,
        "size": "1024x1024",
        "quality": "hd" if quality == "hd" else "standard",
        "n": 1,
        "response_format": "b64_json",
    }
    with httpx.Client(timeout=90.0) as client:
        res = client.post(
            IMAGE_GENERATIONS_API,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if res.status_code >= 400:
            return None, _parse_openai_error(res)
        return res.json(), None


def _extract_image_b64(data: dict[str, Any]) -> tuple[str | None, str | None]:
    items = data.get("data") or []
    if not items:
        return None, None
    item = items[0]
    return item.get("b64_json"), item.get("url")


def _store_result(
    *,
    user_id: str,
    b64: str | None,
    url: str | None,
    prompt: str,
    quality: str,
    model: str,
    style_mode: str,
) -> tuple[str | None, dict[str, Any] | None]:
    from app.services.publish_media import decode_image_data, store_publish_image_for_client

    public_url = url or ""
    if not public_url and b64:
        data_url = f"data:image/png;base64,{b64}"
        raw, mime = decode_image_data(data_url)
        public_url = store_publish_image_for_client(user_id, raw, mime)
    elif public_url.startswith("data:"):
        raw, mime = decode_image_data(public_url)
        public_url = store_publish_image_for_client(user_id, raw, mime)
    elif public_url.startswith("http"):
        try:
            raw, mime = decode_image_data(public_url)
            public_url = store_publish_image_for_client(user_id, raw, mime)
        except Exception:  # noqa: BLE001
            pass

    if not public_url:
        return None, {"ok": False, "error": "No se pudo almacenar la imagen generada", "code": "storage_error"}

    cost = GEMINI_HD_COST_USD if quality == "hd" else GEMINI_STD_COST_USD
    log_prompt = f"[ref:{style_mode}] {prompt[:500]}"
    try:
        supabase_db.insert_generated_image(
            user_id=user_id,
            prompt=log_prompt,
            quality=quality,
            model=model,
            public_url=public_url,
            estimated_cost_usd=cost,
        )
    except Exception:  # noqa: BLE001
        logger.warning("[OPENAI:REF-IMG] log insert failed")

    return public_url, None


def validate_reference_image(reference_data: bytes, content_type: str | None) -> dict[str, Any] | None:
    if not reference_data:
        return {"ok": False, "error": "Imagen de referencia vacía", "code": "invalid_image"}
    if len(reference_data) > MAX_REFERENCE_BYTES:
        return {
            "ok": False,
            "error": "Imagen demasiado grande. Máximo 5 MB.",
            "code": "file_too_large",
        }
    mime = (content_type or "image/jpeg").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIMES:
        return {
            "ok": False,
            "error": "Formato no soportado. Usa JPG, PNG, WebP o GIF.",
            "code": "invalid_format",
        }
    if len(reference_data) < 512:
        return {
            "ok": False,
            "error": "Archivo demasiado pequeño para ser una imagen válida.",
            "code": "invalid_image",
        }
    return None


def generate_image_with_reference(
    *,
    user_id: str,
    prompt: str,
    reference_image: bytes,
    content_type: str | None = "image/jpeg",
    style_mode: str = "inspired",
    quality: str | None = "standard",
) -> dict[str, Any]:
    """
    Genera imagen basada en referencia visual.

    Modos: inspired | variation | edit
    """
    try:
        return _generate_image_with_reference_impl(
            user_id=user_id,
            prompt=prompt,
            reference_image=reference_image,
            content_type=content_type,
            style_mode=style_mode,
            quality=quality,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[REF-IMG] unexpected failure user=%s", user_id[:8])
        return {
            "ok": False,
            "error": "No pude generar la imagen con referencia. Reintenta en unos segundos.",
            "code": "internal_error",
        }


def _generate_image_with_reference_impl(
    *,
    user_id: str,
    prompt: str,
    reference_image: bytes,
    content_type: str | None = "image/jpeg",
    style_mode: str = "inspired",
    quality: str | None = "standard",
) -> dict[str, Any]:
    settings = get_settings()
    google_key = settings.google_api_key.strip()
    api_key = settings.openai_api_key.strip()

    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Indica qué quieres generar o cambiar", "code": "empty_prompt"}

    mode = style_mode if style_mode in ("inspired", "variation", "edit") else "inspired"

    from app.services.marketing_creative import (
        build_marketing_creative_brief,
        should_build_creative_brief,
    )

    display_label = ""
    if should_build_creative_brief(topic, history=None, has_reference_image=True):
        topic, display_label, brief_mode = build_marketing_creative_brief(
            topic,
            history=None,
            has_reference_image=True,
        )
        mode = brief_mode
    mime = (content_type or "image/jpeg").split(";")[0].strip().lower()

    validation_err = validate_reference_image(reference_image, mime)
    if validation_err:
        return validation_err

    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        plan_allows_hd = True
    else:
        limits, _reason, _trial = effective_plan_limits(user_id)
        plan_allows_hd = limits.ai_images_hd_per_day > 0

    picked = _pick_quality(quality, plan_allows_hd=plan_allows_hd)
    if quality == "hd" and not plan_allows_hd:
        picked = "standard"

    quota_err = _check_image_quota(user_id, picked)
    if quota_err:
        return quota_err

    if google_key:
        from app.services.gemini_images import generate_image_with_reference_gemini

        gemini_result = generate_image_with_reference_gemini(
            prompt=topic,
            reference_image=reference_image,
            content_type=mime,
            style_mode=mode,
            quality=picked,
        )
        if gemini_result.get("ok"):
            raw = gemini_result.get("raw_bytes")
            out_mime = str(gemini_result.get("mime_type") or "image/png")
            model_used = str(gemini_result.get("model") or "gemini-image")
            if isinstance(raw, (bytes, bytearray)) and raw:
                public_url, store_err = _store_result(
                    user_id=user_id,
                    b64=base64.b64encode(bytes(raw)).decode("utf-8"),
                    url=None,
                    prompt=topic,
                    quality=picked,
                    model=model_used,
                    style_mode=mode,
                )
                if store_err:
                    return store_err
                cost = float(gemini_result.get("estimated_cost_usd") or GEMINI_STD_COST_USD)
                caption = (display_label or "").strip() or topic[:120]
                return {
                    "ok": True,
                    "success": True,
                    "image_url": public_url,
                    "url": public_url,
                    "prompt": topic,
                    "display_label": caption,
                    "caption": caption,
                    "style_mode": mode,
                    "quality": picked,
                    "model": model_used,
                    "used_fallback": False,
                    "provider": "gemini",
                    "estimated_cost_usd": cost,
                }
        if not api_key:
            return {
                "ok": False,
                "error": str(gemini_result.get("error") or "No pude generar con referencia en Gemini."),
                "code": str(gemini_result.get("code") or "gemini_error"),
            }
        return {
            "ok": False,
            "error": str(gemini_result.get("error") or "No pude generar con referencia en Gemini."),
            "code": str(gemini_result.get("code") or "gemini_error"),
        }

    return {
        "ok": False,
        "error": "Configura GOOGLE_API_KEY en Railway para imágenes con referencia.",
        "code": "config_error",
    }
