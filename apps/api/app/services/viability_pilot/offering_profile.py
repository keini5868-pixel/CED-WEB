"""Perfil de oferta — prioriza nombre propio del usuario + canal (MLM/retail)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# "producto llamado X", "named X", FitLine Basics, marcas Capitalizadas
_NAMED_PRODUCT = re.compile(
    r"(?:"
    r"(?:producto|product|servicio|service|marca|brand|llamad[oa]|named|called)\s+"
    r"[\"'«]?([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ0-9&.''-]{1,40}"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ0-9&.''-]{1,40}){0,4})[\"'»]?"
    r"|[\"'«]([A-ZÁÉÍÓÚÑ][^\"'»]{2,60})[\"'»]"
    r")",
    re.UNICODE,
)

_MLM_HINTS = re.compile(
    r"\b("
    r"mlm|multi[- ]?level|multinivel|venta\s+directa|direct\s+selling|"
    r"network\s+marketing|distribuidor(?:es)?|distributor(?:s)?|"
    r"amway|herbalife|nuskin|nu\s*skin|pm\s*international|fitline|"
    r"unicity|forever\s+living|jeunesse|doTERRA|young\s+living"
    r")\b",
    re.I,
)

_SURFACE_STOP = re.compile(
    r"\b("
    r"naranja|orange|lim[oó]n|lemon|vainilla|vanilla|chocolate|fresa|strawberry|"
    r"en\s+polvo|powder|c[aá]psulas?|capsules?|tabletas?|gummies|gomitas|"
    r"sabor|flavor|flavour|color|pack|empaque|botella|frasco"
    r")\b",
    re.I,
)


def extract_named_products_from_text(text: str) -> list[str]:
    """Nombres propios explícitos en el prompt del usuario (no de la imagen)."""
    raw = (text or "").strip()
    if not raw:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in _NAMED_PRODUCT.finditer(raw):
        name = (m.group(1) or m.group(2) or "").strip(" .,;:")
        name = re.sub(r"\s+", " ", name)
        if len(name) < 3 or len(name) > 70:
            continue
        # Evitar capturar frases enteras de instrucción
        low = name.lower()
        if any(
            bad in low
            for bad in (
                "mercado",
                "estados unidos",
                "united states",
                "estrategia",
                "precios",
                "analiza",
            )
        ):
            continue
        key = low
        if key in seen:
            continue
        seen.add(key)
        found.append(name)
    return found[:3]


def detect_mlm_hint(text: str) -> bool:
    return bool(_MLM_HINTS.search(text or ""))


def _heuristic_profile(
    *,
    text_input: str,
    offering: str,
) -> dict[str, Any]:
    named = extract_named_products_from_text(text_input)
    product_name = named[0] if named else ""
    blob = text_input or offering
    focus_src = product_name or _SURFACE_STOP.sub(" ", blob)
    focus = re.sub(r"\s+", " ", focus_src).strip(" ,.-")[:140] or blob[:120]
    channel = "mlm_direct" if detect_mlm_hint(blob) else ""
    return {
        "product_name": product_name,
        "brand": "",
        "search_focus": focus,
        "category": "",
        "use_case": "",
        "channel": channel,
        "notes": "heuristic",
    }


def summarize_offering_profile(
    offering: str,
    *,
    text_input: str = "",
    image_description: str = "",
) -> dict[str, Any]:
    """Perfil de búsqueda: nombre propio del usuario > categoría genérica de imagen."""
    text_input = (text_input or "").strip()
    image_description = (image_description or "").strip()
    offering = (offering or "").strip() or text_input
    named = extract_named_products_from_text(text_input)
    if len(offering) < 8 and not named:
        return _heuristic_profile(text_input=text_input, offering=offering)

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return _heuristic_profile(text_input=text_input, offering=offering)

    prompt = (
        "Perfil de producto para estudio de competencia y precios. Devuelve JSON:\n"
        "- product_name: nombre EXACTO del producto si el USUARIO lo nombró "
        "(ej. 'FitLine Basics'). Si no hay nombre propio, string vacío.\n"
        "- brand: marca/empresa si aparece (ej. 'PM International', 'FitLine').\n"
        "- search_focus: ancla de búsqueda. Si hay product_name, DEBE empezar por "
        "ese nombre exacto (+ marca si ayuda). NO sustituyas un nombre propio por "
        "una categoría genérica ('suplemento de fibra').\n"
        "- category: categoría de mercado (ej. 'fibra + probióticos', 'MLM wellness').\n"
        "- use_case: para qué lo compra el cliente (1 frase corta).\n"
        "- channel: uno de: retail | ecommerce | mlm_direct | service | unknown. "
        "Usa mlm_direct si es multinivel / venta directa / network marketing / "
        "solo por distribuidores (no Amazon/supermercado).\n"
        "- distractors: atributos a ignorar (sabor, color, formato).\n"
        "REGLAS:\n"
        "1) El TEXTO DEL USUARIO manda sobre la descripción de imagen.\n"
        "2) Si el usuario dijo un nombre de producto, no lo borres ni lo genéricas.\n"
        "3) No inventes marcas.\n"
        f"TEXTO_USUARIO:\n{(text_input or offering)[:700]}\n\n"
        f"DESCRIPCION_IMAGEN (secundaria):\n{(image_description or '(ninguna)')[:500]}\n"
    )
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.05,
                max_output_tokens=500,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (getattr(response, "text", None) or "").strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            return _heuristic_profile(text_input=text_input, offering=offering)

        product_name = str(data.get("product_name") or "").strip()[:80]
        brand = str(data.get("brand") or "").strip()[:80]
        # Prefer regex-captured name from user text if LLM dropped it
        if named and (
            not product_name
            or named[0].lower() not in product_name.lower()
            and product_name.lower() not in named[0].lower()
        ):
            # If LLM invented empty/wrong, restore user-named product
            if not product_name or product_name.lower() in {
                "suplemento",
                "supplement",
                "producto",
                "product",
            }:
                product_name = named[0]
            elif named[0].lower() not in (product_name + " " + brand).lower():
                product_name = named[0]

        focus = str(data.get("search_focus") or "").strip()[:140]
        category = str(data.get("category") or "").strip()[:100]
        use_case = str(data.get("use_case") or "").strip()[:160]
        channel = str(data.get("channel") or "unknown").strip().lower()[:32]
        if channel not in {
            "retail",
            "ecommerce",
            "mlm_direct",
            "service",
            "unknown",
        }:
            channel = "unknown"
        if detect_mlm_hint(text_input) or detect_mlm_hint(product_name + " " + brand):
            channel = "mlm_direct"

        # Enforce: named product must lead search_focus
        if product_name:
            if product_name.lower() not in focus.lower():
                focus = (
                    f"{product_name} {brand} {category}".strip()
                    if brand and brand.lower() not in product_name.lower()
                    else f"{product_name} {category}".strip()
                )
            focus = focus[:140]

        if not focus:
            return _heuristic_profile(text_input=text_input, offering=offering)

        return {
            "product_name": product_name,
            "brand": brand,
            "search_focus": focus,
            "category": category,
            "use_case": use_case,
            "channel": channel,
            "notes": "llm",
        }
    except Exception:  # noqa: BLE001
        logger.warning("[VIABILITY-PILOT] offering profile failed", exc_info=True)
        return _heuristic_profile(text_input=text_input, offering=offering)


def profile_for_report(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_name": profile.get("product_name") or "",
        "brand": profile.get("brand") or "",
        "search_focus": profile.get("search_focus") or "",
        "category": profile.get("category") or "",
        "use_case": profile.get("use_case") or "",
        "channel": profile.get("channel") or "",
    }
