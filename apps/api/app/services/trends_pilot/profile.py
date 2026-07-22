"""Perfil de industria — ancla literal; no generalizar nombres propios."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_NAMED = re.compile(
    r"(?:"
    r"(?:producto|product|marca|brand|rubro|nicho|llamad[oa]|named|called)\s+"
    r"[\"'«]?([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ0-9&.''-]{1,40}"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ0-9&.''-]{1,40}){0,4})[\"'»]?"
    r"|[\"'«]([A-ZÁÉÍÓÚÑ][^\"'»]{2,50})[\"'»]"
    r")",
    re.UNICODE,
)


def extract_named_anchors(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        name = re.sub(r"\s+", " ", name).strip(" .,;:")
        if len(name) < 3 or len(name) > 70:
            return
        low = name.lower()
        if any(
            bad in low
            for bad in (
                "estados unidos",
                "united states",
                "mercado",
                "tendencias",
                "industria",
                "marketing digital",
            )
        ):
            return
        if low in seen:
            return
        seen.add(low)
        found.append(name)

    for m in _NAMED.finditer(text or ""):
        _add(m.group(1) or m.group(2) or "")

    # Title-Case runs (FitLine Basics) even without "llamado"
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9&.-]{2,}(?:\s+[A-Z][A-Za-z0-9&.-]{2,}){1,3})\b",
        text or "",
    ):
        _add(m.group(1))

    return found[:3]


def build_industry_profile(description: str) -> dict[str, Any]:
    text = (description or "").strip()
    named = extract_named_anchors(text)
    heuristic_anchor = named[0] if named else re.sub(r"\s+", " ", text)[:140]

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key or len(text) < 8:
        return {
            "anchor": heuristic_anchor,
            "industry_label": heuristic_anchor[:80],
            "niche_terms": named,
            "named_entities": named,
            "notes": "heuristic",
        }

    prompt = (
        "Perfil de industria para análisis de TENDENCIAS. JSON con:\n"
        "- anchor: string de búsqueda. Si el usuario nombró marca/producto/nicho "
        "propio, ese nombre EXACTO debe ser el ancla (no lo amplíes a categoría "
        "genérica). Si solo describió un rubro, usa su wording concreto.\n"
        "- industry_label: etiqueta corta del rubro.\n"
        "- niche_terms: lista de términos específicos del usuario.\n"
        "- named_entities: nombres propios detectados.\n"
        "PROHIBIDO subir 'vendo FitLine' a 'suplementos genéricos'.\n"
        f"Texto usuario:\n{text[:800]}"
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
                max_output_tokens=400,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = (getattr(response, "text", None) or "").strip()
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            raise ValueError("bad profile json")
        anchor = str(data.get("anchor") or "").strip()[:140]
        # Enforce named entity in anchor
        if named and not any(n.lower() in anchor.lower() for n in named):
            anchor = f"{named[0]} {anchor}".strip()[:140]
        if not anchor:
            anchor = heuristic_anchor
        niche = data.get("niche_terms") if isinstance(data.get("niche_terms"), list) else named
        entities = (
            data.get("named_entities")
            if isinstance(data.get("named_entities"), list)
            else named
        )
        return {
            "anchor": anchor,
            "industry_label": str(data.get("industry_label") or anchor)[:100],
            "niche_terms": [str(x)[:60] for x in niche][:8],
            "named_entities": [str(x)[:60] for x in entities][:5],
            "notes": "llm",
        }
    except Exception:  # noqa: BLE001
        logger.warning("[TRENDS-PILOT] profile failed", exc_info=True)
        return {
            "anchor": heuristic_anchor,
            "industry_label": heuristic_anchor[:80],
            "niche_terms": named,
            "named_entities": named,
            "notes": "heuristic",
        }
