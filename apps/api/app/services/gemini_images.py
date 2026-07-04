"""Generación de imágenes vía Gemini (GOOGLE_API_KEY) — único path de imágenes CED."""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

from app.config import get_settings
from app.deps.auth import is_super_admin
from app.deps.plan_access import effective_plan_limits
from app.domain.plans import PlanId, get_plan_limits
from app.services import supabase_db

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_IMAGE_MODELS = ("gemini-2.5-flash-image",)
DEPRECATED_GEMINI_IMAGE_MODELS = frozenset(
    {
        "gemini-2.0-flash-preview-image-generation",
        "gemini-2.5-flash-image-preview",
    }
)
GEMINI_STD_COST_USD = 0.01
GEMINI_HD_COST_USD = 0.02

_SOCIAL_AD_CONTEXT = re.compile(
    r"\b(facebook|instagram|meta|anuncio|ads|publicidad|redes|post|flyer|banner)\b",
    re.I,
)
_PRODUCT_CONTEXT = re.compile(
    r"\b(producto|empaque|mockup|marca|logo|botella|lata|bolsa|servicio)\b",
    re.I,
)
_IMAGE_INSTRUCTION_PREFIX = re.compile(
    r"^(?:"
    r"(?:me\s+)?(?:puedes\s+|podr[ií]as\s+)?"
    r"(?:gener(?:a(?:r|me|mos|s|is|n|do)?|ame|áme)|cre(?:a(?:r|me|mos|s|is|n|do)?|ame|áme)|"
    r"haz(?:me|nos|lo|la|es|emos|er|go)?|hacer(?:me|lo)?|"
    r"dise[nñ]a(?:r|me|mos|s|is|n|do)?|dibuja(?:r|me|mos|s)?|pinta(?:r|me|mos|s)?"
    r")"
    r"\s+(?:una?\s+)?"
    r"(?:imagen|foto|picture|ilustraci[oó]n|dise[nñ]o|creativo|arte|gr[aá]fico|banner|flyer|portada)"
    r"\s+(?:de|con|para|que\s+)?\s*"
    r")+",
    re.I,
)
_VAGUE_PRODUCT_REF = re.compile(
    r"\b(el producto|ese producto|esta producto|lo mismo|"
    r"esa informaci[oó]n|esos beneficios|esas caracter[ií]sticas|"
    r"sus?\s+(?:especificaciones|beneficios|veneficios|caracter[ií]sticas))\b",
    re.I,
)
_SPECS_BENEFITS = re.compile(
    r"\b(especificaciones|beneficios|veneficios|ingredientes|caracter[ií]sticas)\b",
    re.I,
)


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
    models: list[str] = []
    if primary and primary not in DEPRECATED_GEMINI_IMAGE_MODELS:
        models.append(primary)
    for model in DEFAULT_GEMINI_IMAGE_MODELS:
        if model not in models:
            models.append(model)
    return tuple(models) or DEFAULT_GEMINI_IMAGE_MODELS


def _friendly_image_error(raw: str) -> str:
    msg = (raw or "").strip()
    lower = msg.lower()
    if "404" in msg or "not found" in lower or "not supported" in lower:
        return (
            "El servicio de imágenes no respondió, señor. "
            "Intente de nuevo en unos segundos."
        )
    return msg[:200] if msg else "No pude generar la imagen con Gemini."


def strip_image_generation_instruction(text: str) -> str:
    """Quita verbos de pedido («genera una imagen de…») y deja el contenido visual."""
    t = (text or "").strip()
    while t:
        stripped = _IMAGE_INSTRUCTION_PREFIX.sub("", t, count=1).strip()
        if stripped == t:
            break
        t = stripped.strip(" ,.:;")
    return t or (text or "").strip()


def _extract_visual_subject(text: str) -> str:
    for pattern in (
        r"\b([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,40})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,40})\b",
        r"\b((?:[\wáéíóúñ]+(?:\s+de\s+[\wáéíóúñ]+)?)\s+(?:producto|servicio|marca|evento|personaje|logo))\b",
        r"\b(producto\s+[^\n,.]{3,60})",
        r"^([^\n.]{8,100})",
    ):
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        if match.lastindex and match.lastindex >= 2:
            subject = f"{match.group(1).strip()} de {match.group(2).strip()}"
        else:
            subject = (match.group(1) if match.lastindex else match.group(0)).strip()
        subject = re.sub(r"\s+", " ", subject)
        if len(subject) >= 4 and subject.lower() not in {"el producto", "ese producto", "la imagen"}:
            return subject
    return text[:120].strip()


def _resolve_vague_subject(topic: str, context: str) -> str:
    if not _VAGUE_PRODUCT_REF.search(topic):
        return topic
    subject = _extract_visual_subject(context)
    if re.search(r"\b(esa informaci[oó]n|esos beneficios|esas caracter[ií]sticas)\b", topic, re.I):
        if subject:
            return f"{subject} con sus beneficios y características principales"
    if subject and subject.lower() not in {"el producto", "ese producto"}:
        return re.sub(
            r"\b(el producto|ese producto|esta producto)\b",
            subject,
            topic,
            count=1,
            flags=re.I,
        )
    return topic


def prepare_image_prompt(user_prompt: str, context: str = "") -> str:
    """Convierte el pedido del usuario + contexto en un brief visual para Gemini."""
    from app.services.copy_quality import augment_image_prompt, normalize_spanish

    topic = strip_image_generation_instruction(user_prompt)
    ctx = (context or "").strip()
    topic = _resolve_vague_subject(topic, ctx)
    merged = topic
    if ctx and (
        len(topic) < 120
        or _VAGUE_PRODUCT_REF.search(topic)
        or (_SPECS_BENEFITS.search(topic) and len(ctx) > 80)
    ):
        merged = f"{topic}. Referencia: {ctx[:900]}"
    merged = normalize_spanish(merged)[:4000]
    return augment_image_prompt(merged, ctx)


def enrich_image_prompt_from_context(prompt: str, context: str = "") -> str:
    """Compat: delega en prepare_image_prompt."""
    return prepare_image_prompt(prompt, context)


def build_image_generation_prompts(user_prompt: str) -> list[str]:
    """Variantes genéricas de prompt para maximizar respuesta con imagen de Gemini."""
    topic = (user_prompt or "").strip()
    if not topic:
        return []

    variants: list[str] = []
    faithful = (
        f"Genera una imagen de alta calidad según este pedido: {topic}. "
        "Composición clara, buena iluminación, resultado profesional."
    )
    variants.append(faithful)

    if _SPECS_BENEFITS.search(topic):
        variants.append(
            "Fotografía de producto premium sobre fondo neutro, composición 1:1, "
            "iluminación de estudio, sin texto incrustado. "
            f"Concepto: {_extract_visual_subject(topic)[:350]}."
        )

    if _SOCIAL_AD_CONTEXT.search(topic):
        social = (
            f"Crea una imagen cuadrada profesional para redes sociales. "
            f"Sujeto: {topic}. Estilo publicitario, fondo limpio, fotorrealista o ilustrado según corresponda."
        )
        product = (
            f"Mockup o fotografía de producto/servicio sobre fondo neutro, composición 1:1. "
            f"{topic[:700]}. Calidad publicitaria, poca tipografía incrustada."
        )
        variants.extend([social, product])
        return variants

    if _PRODUCT_CONTEXT.search(topic):
        product = (
            f"Fotografía o mockup profesional de producto/servicio. "
            f"{topic[:700]}. Iluminación de estudio, fondo limpio."
        )
        clean = (
            f"Imagen comercial elegante, enfoque en el sujeto principal: {topic[:600]}."
        )
        variants.extend([product, clean])
        return variants

    illustrated = (
        f"Ilustración o fotografía detallada: {topic[:650]}. "
        "Estilo coherente con el tema, sin marcas de agua."
    )
    simplified = f"Imagen visual clara y atractiva: {topic[:500]}."
    variants.extend([illustrated, simplified])
    return variants


def _extract_text_from_response(response: Any) -> str:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(str(text).strip())
    return " ".join(chunks).strip()


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


def _generate_content_config(*, quality: str, temperature: float) -> Any:
    from google.genai import types

    image_config = None
    if hasattr(types, "ImageConfig"):
        image_config = types.ImageConfig(aspect_ratio="1:1")
    return types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        temperature=temperature,
        **({"image_config": image_config} if image_config else {}),
    )


def generate_image_gemini(
    *,
    prompt: str,
    quality: str = "standard",
    context: str = "",
) -> dict[str, Any]:
    """Genera imagen con Gemini. Requiere GOOGLE_API_KEY."""
    from google import genai
    from app.services.copy_quality import augment_image_prompt

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Prompt vacío"}
    if not api_key:
        return {"ok": False, "error": "GOOGLE_API_KEY no configurada", "code": "config_error"}

    client = genai.Client(api_key=api_key)
    last_error = "No pude generar la imagen con Gemini."
    raw_variants = build_image_generation_prompts(topic) or [topic[:4000]]
    prompt_variants = [augment_image_prompt(variant, context) for variant in raw_variants]

    for model in _image_models():
        for attempt, variant in enumerate(prompt_variants):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=variant[:4000],
                    config=_generate_content_config(
                        quality=quality,
                        temperature=0.85 if attempt else 0.9,
                    ),
                )
                payload = _extract_image_payload(response)
                if payload:
                    raw, mime = payload
                    logger.info(
                        "[GEMINI:IMAGE] ok model=%s attempt=%s bytes=%s",
                        model,
                        attempt,
                        len(raw),
                    )
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
                text_part = _extract_text_from_response(response)
                if text_part:
                    last_error = text_part[:200]
                else:
                    last_error = f"Gemini ({model}) no devolvió imagen usable"
                logger.warning(
                    "[GEMINI:IMAGE] empty model=%s attempt=%s text=%s",
                    model,
                    attempt,
                    (text_part or "")[:120],
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:200]
                logger.warning(
                    "[GEMINI:IMAGE] model=%s attempt=%s error: %s",
                    model,
                    attempt,
                    last_error,
                )

    hint = (
        " Intente un pedido más concreto, por ejemplo: "
        "'genera una imagen de un atardecer en la playa con estilo fotorrealista'."
    )
    friendly = _friendly_image_error(last_error)
    if "no devolvió imagen" in last_error.lower() or "no devolvió imagen" in friendly.lower():
        friendly = f"{friendly}{hint}"
    return {"ok": False, "error": friendly, "code": "gemini_error"}


def generate_image_with_reference_gemini(
    *,
    prompt: str,
    reference_image: bytes,
    content_type: str = "image/jpeg",
    style_mode: str = "inspired",
    quality: str = "standard",
) -> dict[str, Any]:
    """Variación / inspiración / edición con imagen de referencia vía Gemini."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {
            "ok": False,
            "error": "Biblioteca Gemini no disponible en el servidor.",
            "code": "config_error",
        }

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

    try:
        from app.services.copy_quality import augment_image_prompt

        enriched = augment_image_prompt(_reference_prompt(topic, mode), topic)
        client = genai.Client(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GEMINI:REF-IMG] setup failed: %s", exc)
        return {"ok": False, "error": _friendly_image_error(str(exc)), "code": "gemini_error"}

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
                config=_generate_content_config(quality=quality, temperature=0.85),
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

    return {"ok": False, "error": _friendly_image_error(last_error), "code": "gemini_error"}


def generate_image(
    *,
    user_id: str,
    plan_id: str | None,
    prompt: str,
    quality: str | None = "auto",
    context: str = "",
    display_label: str | None = None,
) -> dict[str, Any]:
    """Genera imagen con Gemini — único provider de imágenes CED."""
    settings = get_settings()
    google_key = settings.google_api_key.strip()
    topic = prepare_image_prompt(prompt, context)
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

    gemini_result = generate_image_gemini(prompt=topic, quality=picked, context=context)
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

    caption = (display_label or "").strip() or "Imagen generada"
    return {
        "ok": True,
        "url": public_url,
        "caption": caption,
        "prompt": caption,
        "quality": picked,
        "model": model,
        "provider": "gemini",
        "estimated_cost_usd": cost,
    }
