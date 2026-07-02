"""Generación de imágenes vía Gemini (GOOGLE_API_KEY) — único path de imágenes CED."""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.config import get_settings
from app.deps.auth import is_super_admin
from app.deps.plan_access import effective_plan_limits
from app.domain.plans import PlanId, get_plan_limits
from app.services import supabase_db

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_IMAGE_MODELS = (
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation",
)
GEMINI_STD_COST_USD = 0.01
GEMINI_HD_COST_USD = 0.02


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


def _day_image_counts(user_id: str) -> tuple[int, int]:
    try:
        return supabase_db.count_generated_images_today(user_id)
    except Exception:  # noqa: BLE001
        return 0, 0


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


def generate_image(
    *,
    user_id: str,
    plan_id: str | None,
    prompt: str,
    quality: str | None = "auto",
) -> dict[str, Any]:
    """Genera imagen con Gemini — único provider de imágenes CED."""
    settings = get_settings()
    google_key = settings.google_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Prompt vacío"}
    if not google_key:
        return {
            "ok": False,
            "error": "Configura GOOGLE_API_KEY en Railway para generar imágenes.",
            "code": "config_error",
        }

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

    gemini_result = generate_image_gemini(prompt=topic, quality=picked)
    if not gemini_result.get("ok"):
        err_detail = str(gemini_result.get("error") or "Gemini falló")
        logger.error("[GEMINI:IMAGE] failed user=%s error=%s", user_id[:8], err_detail[:200])
        return {
            "ok": False,
            "error": err_detail,
            "code": str(gemini_result.get("code") or "gemini_error"),
        }

    raw = gemini_result.get("raw_bytes")
    mime = str(gemini_result.get("mime_type") or "image/png")
    model = str(gemini_result.get("model") or "gemini-2.5-flash-image")
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return {"ok": False, "error": "Gemini no devolvió imagen usable", "code": "gemini_error"}

    from app.services.publish_media import store_publish_image_for_client

    public_url = store_publish_image_for_client(user_id, bytes(raw), mime)
    cost = float(gemini_result.get("estimated_cost_usd") or GEMINI_STD_COST_USD)
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
        logger.warning("[GEMINI:IMAGE] log insert failed")

    return {
        "ok": True,
        "url": public_url,
        "quality": picked,
        "model": model,
        "provider": "gemini",
        "estimated_cost_usd": cost,
    }
