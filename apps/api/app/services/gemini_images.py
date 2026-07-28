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

DEFAULT_GEMINI_IMAGE_MODELS = (
    "gemini-3.1-flash-image",  # Nano Banana 2 (calidad Studio actual)
    "gemini-2.5-flash-image",  # Nano Banana original — fallback
)
DEPRECATED_GEMINI_IMAGE_MODELS = frozenset(
    {
        "gemini-2.0-flash-preview-image-generation",
        "gemini-2.5-flash-image-preview",
    }
)
# COGS API pagada Google (1K / ~2K) — no es el free tier de AI Studio.
# Fuente: ai.google.dev/gemini-api/docs/pricing (Gemini 3.1 Flash Image).
GEMINI_STD_COST_USD = 0.067
GEMINI_HD_COST_USD = 0.101
NANO_BANANA_MODEL_LABEL = "nano-banana-2"

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
    r"(?:\s+(?:de|con|para|que\s+)?(?:estas?\s+caracter[ií]sticas\s*)?)?"
    r"\s*"
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
_NO_META_TEXT_ON_IMAGE = (
    "Sin texto, tipografía, subtítulos, marcas de agua ni etiquetas en la imagen."
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


def _day_image_counts(user_id: str) -> tuple[int, int, int]:
    try:
        return supabase_db.count_generated_images_today(user_id)
    except Exception:  # noqa: BLE001
        return 0, 0, 0


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


def strip_image_prompt_meta(text: str) -> str:
    """Elimina wrappers internos que Gemini suele renderizar como tipografía."""
    from app.services.copy_quality import strip_prompt_meta_for_image

    return strip_prompt_meta_for_image(text)


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
    """Convierte el pedido del usuario + contexto en un brief visual para Gemini.

    Devuelve SOLO descripción visual (+ reglas anti-fuga / textos literales si aplica).
    Nunca incluye wrappers tipo «Instrucciones actuales…» o «Genera una imagen según…».
    """
    from app.services.copy_quality import augment_image_prompt, normalize_spanish

    topic = strip_image_prompt_meta(strip_image_generation_instruction(user_prompt))
    ctx_raw = strip_image_prompt_meta(context or "")
    topic = _resolve_vague_subject(topic, ctx_raw)
    merged = topic
    if ctx_raw and (
        len(topic) < 120
        or _VAGUE_PRODUCT_REF.search(topic)
        or (_SPECS_BENEFITS.search(topic) and len(ctx_raw) > 80)
    ):
        # Hechos visuales del historial — sin etiquetas meta que el modelo pinte.
        facts = ctx_raw[:900].strip()
        if facts and facts.lower() not in merged.lower():
            merged = f"{topic}. {facts}"
    merged = normalize_spanish(merged)[:4000]
    return augment_image_prompt(merged, ctx_raw)


def enrich_image_prompt_from_context(prompt: str, context: str = "") -> str:
    """Compat: delega en prepare_image_prompt."""
    return prepare_image_prompt(prompt, context)


def build_image_generation_prompts(user_prompt: str) -> list[str]:
    """Variantes visuales para Gemini — sin wrappers de instrucción que se pinten en la foto."""
    topic = strip_image_prompt_meta(strip_image_generation_instruction(user_prompt or ""))
    if not topic:
        return []

    variants: list[str] = []
    # Descripción directa del sujeto; la anti-fuga va al final (no como “título” legible).
    faithful = (
        f"{topic}. Alta calidad, composición clara, buena iluminación, resultado profesional. "
        f"{_NO_META_TEXT_ON_IMAGE}"
    )
    variants.append(faithful)

    if _SPECS_BENEFITS.search(topic):
        variants.append(
            "Fotografía de producto premium sobre fondo neutro, composición 1:1, "
            "iluminación de estudio, sin texto incrustado. "
            f"Concepto: {_extract_visual_subject(topic)[:350]}. {_NO_META_TEXT_ON_IMAGE}"
        )

    if _SOCIAL_AD_CONTEXT.search(topic):
        social = (
            f"Imagen cuadrada profesional para redes sociales. "
            f"Sujeto: {topic[:700]}. Estilo publicitario, fondo limpio. {_NO_META_TEXT_ON_IMAGE}"
        )
        product = (
            f"Mockup o fotografía de producto/servicio sobre fondo neutro, composición 1:1. "
            f"{topic[:700]}. Calidad publicitaria. {_NO_META_TEXT_ON_IMAGE}"
        )
        variants.extend([social, product])
        return variants

    if _PRODUCT_CONTEXT.search(topic):
        product = (
            f"Fotografía o mockup profesional de producto/servicio. "
            f"{topic[:700]}. Iluminación de estudio, fondo limpio. {_NO_META_TEXT_ON_IMAGE}"
        )
        clean = (
            f"Imagen comercial elegante, enfoque en el sujeto principal: {topic[:600]}. "
            f"{_NO_META_TEXT_ON_IMAGE}"
        )
        variants.extend([product, clean])
        return variants

    illustrated = (
        f"Ilustración o fotografía detallada: {topic[:650]}. "
        f"Estilo coherente con el tema, sin marcas de agua. {_NO_META_TEXT_ON_IMAGE}"
    )
    simplified = f"{topic[:500]}. Imagen visual clara y atractiva. {_NO_META_TEXT_ON_IMAGE}"
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
    topic = strip_image_prompt_meta(
        strip_image_generation_instruction(user_prompt or "")
    ) or "nueva versión de la imagen de referencia"
    anti = _NO_META_TEXT_ON_IMAGE
    if style_mode == "inspired":
        return (
            f"Misma esencia visual (estilo, paleta, composición) que la imagen adjunta. "
            f"Escena pedida: {topic}. {anti}"
        )
    if style_mode == "variation":
        return (
            f"Variación de la imagen adjunta. Cambios pedidos: {topic}. "
            f"Conserva estilo y tonos clave. {anti}"
        )
    if style_mode == "edit":
        return (
            f"Edición de la imagen adjunta: {topic}. "
            f"Mantén intacto lo no pedido. {anti}"
        )
    return f"{topic}. {anti}"


def _prepare_reference_gemini_prompt(prompt: str, mode: str) -> str:
    """Evita doble envoltorio y fuga del prompt en creativos con texto."""
    from app.services.copy_quality import augment_image_prompt
    from app.services.marketing_creative import CREATIVO_PROMPT_MARKER

    p = strip_image_prompt_meta((prompt or "").strip())
    if p.startswith(CREATIVO_PROMPT_MARKER):
        return p[:3800]
    base = _reference_prompt(p, mode)
    return augment_image_prompt(base, "")


def _generate_content_config(
    *,
    quality: str,
    temperature: float,
    modalities: list[str] | None = None,
) -> Any:
    from google.genai import types

    mods = modalities or ["IMAGE"]
    image_config = None
    if hasattr(types, "ImageConfig"):
        try:
            image_config = types.ImageConfig(aspect_ratio="1:1")
        except TypeError:
            image_config = None
    return types.GenerateContentConfig(
        response_modalities=mods,
        temperature=temperature,
        **({"image_config": image_config} if image_config else {}),
    )


def generate_image_gemini(
    *,
    prompt: str,
    quality: str = "standard",
    context: str = "",
) -> dict[str, Any]:
    """Genera imagen con Gemini. Requiere GOOGLE_API_KEY.

    `prompt` debe ser un brief visual (salida de prepare_image_prompt).
    No reinyecta wrappers meta del chat ni vuelve a pegar el context etiquetado.
    """
    from google import genai

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    topic = strip_image_prompt_meta((prompt or "").strip())
    if not topic:
        return {"ok": False, "error": "Prompt vacío"}
    if not api_key:
        return {"ok": False, "error": "GOOGLE_API_KEY no configurada", "code": "config_error"}
    if _NO_META_TEXT_ON_IMAGE[:40] not in topic:
        topic = f"{topic} {_NO_META_TEXT_ON_IMAGE}"

    client = genai.Client(api_key=api_key)
    try:
        from google.genai import types as _genai_types

        client = genai.Client(
            api_key=api_key,
            http_options=_genai_types.HttpOptions(timeout=120_000),
        )
    except Exception:  # noqa: BLE001 — SDK sin soporte de http_options.timeout
        client = genai.Client(api_key=api_key)
    last_error = "No pude generar la imagen con Gemini."
    # Primario: brief ya preparado. Fallbacks: variantes cortas del sujeto visual puro.
    prompt_variants: list[str] = [topic[:4000]]
    visual_core = re.split(
        r"(?:Ortografía española|TEXTOS EXACTOS|Minimiza texto|No dibujes texto)",
        topic,
        maxsplit=1,
    )[0].strip(" .")
    visual_core = strip_image_prompt_meta(strip_image_generation_instruction(visual_core))
    for variant in build_image_generation_prompts(visual_core)[1:]:
        if variant not in prompt_variants:
            prompt_variants.append(variant[:4000])
    # `context` se ignora aquí a propósito: prepare_image_prompt ya incorporó hechos limpios.
    _ = context

    for model in _image_models():
        for attempt, variant in enumerate(prompt_variants):
            # IMAGE-only evita respuestas de solo texto (alucinación de prompt).
            for modalities in (["IMAGE"], ["TEXT", "IMAGE"]):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=variant[:4000],
                        config=_generate_content_config(
                            quality=quality,
                            temperature=0.85 if attempt else 0.9,
                            modalities=modalities,
                        ),
                    )
                    payload = _extract_image_payload(response)
                    if payload:
                        raw, mime = payload
                        # Rechazar "imágenes" que son texto en PNG vacío / demasiado chicas
                        if len(raw) < 2_000:
                            last_error = "Gemini devolvió un payload de imagen inválido"
                            continue
                        logger.info(
                            "[GEMINI:IMAGE] ok model=%s attempt=%s mods=%s bytes=%s",
                            model,
                            attempt,
                            "+".join(modalities),
                            len(raw),
                        )
                        return {
                            "ok": True,
                            "raw_bytes": raw,
                            "mime_type": mime,
                            "model": model,
                            "quality": quality,
                            "provider": "gemini",
                            "engine": NANO_BANANA_MODEL_LABEL,
                            "estimated_cost_usd": (
                                GEMINI_HD_COST_USD if quality == "hd" else GEMINI_STD_COST_USD
                            ),
                        }
                    text_part = _extract_text_from_response(response)
                    if text_part:
                        # Nunca devolver el texto del modelo como si fuera la imagen.
                        last_error = (
                            "El modelo respondió con texto en vez de imagen. "
                            f"Detalle: {text_part[:120]}"
                        )
                    else:
                        last_error = f"Gemini ({model}) no devolvió imagen usable"
                    logger.warning(
                        "[GEMINI:IMAGE] empty model=%s attempt=%s mods=%s text=%s",
                        model,
                        attempt,
                        "+".join(modalities),
                        (text_part or "")[:120],
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)[:200]
                    logger.warning(
                        "[GEMINI:IMAGE] model=%s attempt=%s mods=%s error: %s",
                        model,
                        attempt,
                        "+".join(modalities),
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
        enriched = _prepare_reference_gemini_prompt(topic, mode)
        try:
            from google.genai import types as _genai_types

            client = genai.Client(
                api_key=api_key,
                http_options=_genai_types.HttpOptions(timeout=120_000),
            )
        except Exception:  # noqa: BLE001
            client = genai.Client(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GEMINI:REF-IMG] setup failed: %s", exc)
        return {"ok": False, "error": _friendly_image_error(str(exc)), "code": "gemini_error"}

    from app.services.marketing_creative import CREATIVO_PROMPT_MARKER

    temp = 0.5 if topic.strip().startswith(CREATIVO_PROMPT_MARKER) else 0.85
    last_error = "No pude generar la imagen con referencia en Gemini."

    for model in _image_models():
        for modalities in (["IMAGE"], ["TEXT", "IMAGE"]):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_bytes(data=reference_image, mime_type=mime),
                                types.Part.from_text(text=enriched[:3800]),
                            ],
                        )
                    ],
                    config=_generate_content_config(
                        quality=quality,
                        temperature=temp,
                        modalities=modalities,
                    ),
                )
                payload = _extract_image_payload(response)
                if payload:
                    raw, out_mime = payload
                    if len(raw) < 2_000:
                        last_error = "Gemini devolvió un payload de imagen inválido"
                        continue
                    logger.info(
                        "[GEMINI:REF-IMG] ok model=%s mode=%s mods=%s bytes=%s",
                        model,
                        mode,
                        "+".join(modalities),
                        len(raw),
                    )
                    return {
                        "ok": True,
                        "raw_bytes": raw,
                        "mime_type": out_mime,
                        "model": model,
                        "quality": quality,
                        "style_mode": mode,
                        "provider": "gemini",
                        "engine": NANO_BANANA_MODEL_LABEL,
                        "estimated_cost_usd": (
                            GEMINI_HD_COST_USD if quality == "hd" else GEMINI_STD_COST_USD
                        ),
                    }
                text_part = _extract_text_from_response(response)
                if text_part:
                    last_error = (
                        "El modelo respondió con texto en vez de imagen. "
                        f"{text_part[:120]}"
                    )
                else:
                    last_error = f"Gemini ({model}) no devolvió imagen con referencia"
                logger.warning(
                    "[GEMINI:REF-IMG] empty model=%s mode=%s mods=%s",
                    model,
                    mode,
                    "+".join(modalities),
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:200]
                logger.warning(
                    "[GEMINI:REF-IMG] model=%s mods=%s error: %s",
                    model,
                    "+".join(modalities),
                    last_error,
                )

    return {"ok": False, "error": _friendly_image_error(last_error), "code": "gemini_error"}


def _finalize_generated_image(
    *,
    user_id: str,
    topic: str,
    display_label: str | None,
    result: dict[str, Any],
    ideogram_declined_reason: str | None = None,
) -> dict[str, Any]:
    raw = result.get("raw_bytes")
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return {"ok": False, "error": "No se generó una imagen usable", "code": "gemini_error"}

    mime = str(result.get("mime_type") or "image/png")
    model = str(result.get("model") or "gemini-3.1-flash-image")
    provider = str(result.get("provider") or "gemini")
    picked = str(result.get("quality") or "standard")

    from app.services.publish_media import store_publish_image_for_client

    public_url = store_publish_image_for_client(user_id, bytes(raw), mime)
    cost = float(result.get("estimated_cost_usd") or GEMINI_STD_COST_USD)
    db_quality = "text" if provider == "ideogram" else picked
    try:
        supabase_db.insert_generated_image(
            user_id=user_id,
            prompt=topic,
            quality=db_quality,
            model=model,
            public_url=public_url,
            estimated_cost_usd=cost,
        )
    except Exception:  # noqa: BLE001
        logger.warning("[IMAGE] log insert failed provider=%s", provider)

    caption = (display_label or "").strip() or "Imagen generada"
    return {
        "ok": True,
        "url": public_url,
        "caption": caption,
        "prompt": caption,
        "quality": picked,
        "model": model,
        "provider": provider,
        "estimated_cost_usd": cost,
        "ideogram_used": provider == "ideogram",
        "ideogram_declined_reason": None if provider == "ideogram" else ideogram_declined_reason,
    }


def _maybe_generate_with_ideogram(
    *,
    user_id: str,
    prefer_ideogram: bool,
    topic: str,
    text_used: int,
    text_cap: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Intenta Ideogram si el pedido lo exige y el plan/monedero lo permite.

    Retorna (resultado_ok_o_None, motivo_de_no_uso). Nunca lanza — cualquier falla
    (config, red, safety, cupo/saldo insuficiente) devuelve (None, motivo) para que el
    llamador degrade a Gemini sin exponer el error al usuario.
    """
    if not prefer_ideogram:
        return None, None
    if text_cap <= 0:
        return None, "basic_excluded"

    settings = get_settings()
    if not settings.ideogram_api_key.strip():
        return None, "not_configured"

    within_quota = text_used < text_cap
    profile = supabase_db.get_profile(user_id) or {}
    admin_bypass = is_super_admin(profile.get("email"), profile.get("role"))
    if not within_quota and not admin_bypass:
        from app.services.wallet import can_afford

        if not can_afford(user_id, "image_text", units=1.0):
            return None, "no_quota_no_balance"

    from app.services.ideogram_images import generate_image_ideogram

    result = generate_image_ideogram(prompt=topic)
    if not result.get("ok"):
        logger.info(
            "[IMAGE:ROUTER] ideogram failed, fallback a Gemini user=%s error=%s",
            user_id[:8],
            str(result.get("error"))[:120],
        )
        return None, "ideogram_failed"

    if not within_quota and not admin_bypass:
        from app.services.wallet import try_spend

        # Siempre 1 unidad ($0.06) — una imagen visible al usuario, nunca N variantes.
        spend = try_spend(user_id, "image_text", units=1.0)
        if not spend.get("ok"):
            logger.warning(
                "[IMAGE:ROUTER] ideogram entregada pero débito de monedero falló user=%s",
                user_id[:8],
            )
        else:
            logger.info(
                "[IMAGE:ROUTER] ideogram wallet charge user=%s charged_usd=%.4f "
                "num_returned=%s",
                user_id[:8],
                float(spend.get("charged_usd") or 0),
                result.get("num_images_returned"),
            )
    else:
        logger.info(
            "[IMAGE:ROUTER] ideogram within free quota user=%s num_returned=%s "
            "provider_request_cost=%.4f admin_bypass=%s",
            user_id[:8],
            result.get("num_images_returned"),
            float(result.get("provider_request_cost_usd") or result.get("estimated_cost_usd") or 0),
            admin_bypass,
        )
    return result, None


def generate_image(
    *,
    user_id: str,
    plan_id: str | None,
    prompt: str,
    quality: str | None = "auto",
    context: str = "",
    display_label: str | None = None,
    prefer_ideogram: bool = False,
) -> dict[str, Any]:
    """Genera imagen — Ideogram si el pedido exige texto legible y el plan lo permite;
    en cualquier otro caso (o si Ideogram falla), Gemini como siempre."""
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

    std_used, hd_used, text_used = _day_image_counts(user_id)

    ideogram_result, ideogram_declined_reason = _maybe_generate_with_ideogram(
        user_id=user_id,
        prefer_ideogram=prefer_ideogram,
        topic=topic,
        text_used=text_used,
        text_cap=limits.ai_images_text_per_day,
    )
    if ideogram_result is not None:
        return _finalize_generated_image(
            user_id=user_id,
            topic=topic,
            display_label=display_label,
            result=ideogram_result,
        )

    picked = _pick_quality(topic, None if quality == "auto" else quality)

    if picked == "hd":
        cap = limits.ai_images_hd_per_day
        used = hd_used
    else:
        cap = limits.ai_images_standard_per_day
        used = std_used

    # Super admin nunca se bloquea por monedero vacío (cuenta de pruebas / ops).
    admin_bypass = is_super_admin(profile.get("email"), profile.get("role"))
    if (cap <= 0 or used >= cap) and not admin_bypass:
        from app.services.wallet import try_spend

        resource = "image_hd" if picked == "hd" else "image_std"
        spend = try_spend(user_id, resource, units=1.0)
        if not spend.get("ok"):
            if cap <= 0:
                return {
                    "ok": False,
                    "error": spend.get("error")
                    or "Tu plan no incluye imágenes. Recarga desde $10 o mejora tu plan.",
                    "code": "needs_recharge",
                }
            return {
                "ok": False,
                "error": spend.get("error")
                or (
                    f"Límite diario de imágenes {picked} alcanzado. "
                    "Recarga desde $10 para continuar."
                ),
                "code": "needs_recharge",
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

    return _finalize_generated_image(
        user_id=user_id,
        topic=topic,
        display_label=display_label,
        result=gemini_result,
        ideogram_declined_reason=ideogram_declined_reason,
    )
