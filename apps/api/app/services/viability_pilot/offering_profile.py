"""Perfil compacto de la oferta — ancla búsquedas y relevancia de competidores."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# Atributos superficiales: NO definen competencia directa.
_SURFACE_STOP = re.compile(
    r"\b("
    r"naranja|orange|lim[oó]n|lemon|vainilla|vanilla|chocolate|fresa|strawberry|"
    r"en\s+polvo|powder|c[aá]psulas?|capsules?|tabletas?|gummies|gomitas|"
    r"sabor|flavor|flavour|color|pack|empaque|botella|frasco"
    r")\b",
    re.I,
)


def _heuristic_profile(offering: str) -> dict[str, str]:
    text = re.sub(r"\s+", " ", (offering or "").strip())
    # Quita ruido superficial para foco de búsqueda
    focus = _SURFACE_STOP.sub(" ", text)
    focus = re.sub(r"\s+", " ", focus).strip(" ,.-")[:120] or text[:120]
    return {
        "search_focus": focus,
        "category": "",
        "use_case": "",
        "notes": "heuristic",
    }


def summarize_offering_profile(offering: str) -> dict[str, str]:
    """Extrae categoría/uso real; ignora sabor/formato como eje de competencia."""
    text = (offering or "").strip()
    if len(text) < 8:
        return _heuristic_profile(text)

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return _heuristic_profile(text)

    prompt = (
        "Analiza esta oferta de producto/servicio para un estudio de competencia. "
        "Devuelve JSON con keys:\n"
        "- search_focus: frase corta (máx 12 palabras) para buscar COMPETIDORES DIRECTOS "
        "(categoría + beneficio/uso). PROHIBIDO usar solo sabor, color o formato "
        "(naranja, en polvo, cápsulas) como eje.\n"
        "- category: categoría de mercado (ej. 'fibra soluble', 'colágeno hidrolizado', "
        "'pre-entreno', 'cafetería de especialidad').\n"
        "- use_case: para qué lo compra el cliente (1 frase).\n"
        "- distractors: lista de atributos superficiales a IGNORAR al juzgar competencia "
        "(sabor, formato, packaging).\n"
        "NO inventes claims médicos. Español o inglés según el input.\n"
        f"Oferta:\n{text[:800]}"
    )
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=400,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (getattr(response, "text", None) or "").strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            return _heuristic_profile(text)
        focus = str(data.get("search_focus") or "").strip()[:140]
        category = str(data.get("category") or "").strip()[:100]
        use_case = str(data.get("use_case") or "").strip()[:160]
        if not focus:
            return _heuristic_profile(text)
        return {
            "search_focus": focus,
            "category": category,
            "use_case": use_case,
            "notes": "llm",
        }
    except Exception:  # noqa: BLE001
        logger.warning("[VIABILITY-PILOT] offering profile failed", exc_info=True)
        return _heuristic_profile(text)


def profile_for_report(profile: dict[str, str]) -> dict[str, Any]:
    return {
        "search_focus": profile.get("search_focus") or "",
        "category": profile.get("category") or "",
        "use_case": profile.get("use_case") or "",
    }
