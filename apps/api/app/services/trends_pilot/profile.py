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


_PHYSICAL_HINT = re.compile(
    r"\b("
    r"figuras?|figurines?|action\s*figures?|coleccion(?:able)?s?|collectibles?|"
    r"juguetes?|toys?|merchandis\w*|estatuas?|statues?|plush|funko|nendoroid|"
    r"poster|impres[oó]n|suplementos?|alimentos?|comida|cafeter\w*|caf[eé]|"
    r"ropa|calzado|muebles?|cosm[eé]tic\w*|perfume|"
    r"f[ií]sico|physical\s*(?:good|product)|retail\s*product"
    r")\b",
    re.I,
)
_DIGITAL_ASSET_HINT = re.compile(
    r"\b(crypto|token|coin|blockchain|nft|defi|memecoin|altcoin|saas|software|"
    r"app\b|plataforma digital)\b",
    re.I,
)


def infer_product_kind(text: str, category: str = "") -> str:
    """physical_good | digital_asset | service | unknown — for off-category filters."""
    blob = f"{text} {category}".strip()
    if _PHYSICAL_HINT.search(blob) and not _DIGITAL_ASSET_HINT.search(blob):
        return "physical_good"
    if _DIGITAL_ASSET_HINT.search(blob) and not _PHYSICAL_HINT.search(blob):
        return "digital_asset"
    if re.search(r"\b(servicio|service|consultor|agencia|agency)\b", blob, re.I):
        return "service"
    return "unknown"


def _heuristic_category(text: str) -> str:
    low = text.lower()
    if re.search(r"figuras?|figurines?|action\s*figures?|coleccion|collectible", low):
        return "coleccionables / action figures"
    if re.search(r"suplemento|fitline|wellness|prote[ií]na", low):
        return "suplementos / wellness"
    if re.search(r"cafeter|caf[eé]\s+de\s+especial", low):
        return "cafetería de especialidad"
    return ""


def build_industry_profile(description: str) -> dict[str, Any]:
    text = (description or "").strip()
    named = extract_named_anchors(text)
    heuristic_anchor = named[0] if named else re.sub(r"\s+", " ", text)[:140]
    heuristic_cat = _heuristic_category(text)

    def _base(**extra: Any) -> dict[str, Any]:
        category = str(extra.get("category") or heuristic_cat)[:100]
        kind = str(extra.get("product_kind") or "").strip()
        if kind not in ("physical_good", "digital_asset", "service", "unknown"):
            kind = infer_product_kind(text, category)
        return {
            "anchor": str(extra.get("anchor") or heuristic_anchor)[:140],
            "industry_label": str(extra.get("industry_label") or heuristic_anchor)[:100],
            "category": category,
            "product_kind": kind,
            "niche_terms": extra.get("niche_terms") or named,
            "named_entities": extra.get("named_entities") or named,
            "notes": extra.get("notes") or "heuristic",
        }

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key or len(text) < 8:
        return _base()

    prompt = (
        "Perfil de industria para análisis de TENDENCIAS. JSON con:\n"
        "- anchor: string de búsqueda. Si el usuario nombró marca/producto/nicho "
        "propio, ese nombre EXACTO debe ser el ancla (no lo amplíes a categoría "
        "genérica). Si solo describió un rubro, usa su wording concreto.\n"
        "- industry_label: etiqueta corta del rubro.\n"
        "- category: categoría de mercado concreta (ej. 'figuras coleccionables anime', "
        "'suplementos MLM', 'cafetería de especialidad').\n"
        "- product_kind: uno de physical_good | digital_asset | service | unknown. "
        "Figuras, merch, comida, ropa = physical_good. Crypto/tokens/NFT/apps = "
        "digital_asset. Consultoría/agencia = service.\n"
        "- niche_terms: lista de términos específicos del usuario.\n"
        "- named_entities: nombres propios detectados.\n"
        "PROHIBIDO subir 'vendo FitLine' a 'suplementos genéricos'.\n"
        "PROHIBIDO confundir personajes/anime merch con criptomonedas del mismo nombre.\n"
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
                max_output_tokens=450,
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
        category = str(data.get("category") or heuristic_cat).strip()[:100]
        kind = str(data.get("product_kind") or "").strip()
        # Prefer physical if user wording clearly says figures/merch
        if infer_product_kind(text, category) == "physical_good":
            kind = "physical_good"
        return _base(
            anchor=anchor,
            industry_label=str(data.get("industry_label") or anchor)[:100],
            category=category,
            product_kind=kind,
            niche_terms=[str(x)[:60] for x in niche][:8],
            named_entities=[str(x)[:60] for x in entities][:5],
            notes="llm",
        )
    except Exception:  # noqa: BLE001
        logger.warning("[TRENDS-PILOT] profile failed", exc_info=True)
        return _base()
