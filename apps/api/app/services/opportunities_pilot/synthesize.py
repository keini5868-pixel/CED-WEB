"""Fusiona curated + search en ficha de lectura."""

from __future__ import annotations

from typing import Any

SECTION_ORDER = (
    ("what_is", "Qué es"),
    ("company_history", "Historia y presencia"),
    ("science_credibility", "Ciencia, calidad, anti-dopaje y deporte"),
    ("social_responsibility", "Responsabilidad social"),
    ("products", "Catálogo FitLine (productos clave)"),
    ("how_it_works", "Cómo funciona"),
    ("store_entry", "Entrar a la tienda / Partner Area (checklist)"),
    ("requirements", "Planes de inscripción"),
    ("income_potential", "Plan de compensación"),
    ("prospecting", "Prospección en redes"),
    ("getting_started", "Pasos para empezar"),
    ("affiliation", "Afiliación"),
    ("risks", "Limitaciones / riesgos"),
)


def build_opportunity_detail(
    plugin: dict[str, Any],
    *,
    search_updates: dict[str, list[dict[str, str]]] | None = None,
    search_meta: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    curated = plugin.get("curated") or {}
    curated_sections = curated.get("sections") or {}
    updates = search_updates or {}
    meta = search_meta or {}
    data_gaps: list[str] = []
    curated_only = bool(meta.get("curated_only")) or meta.get("live_search") is False

    if curated_only:
        # Servir ficha fija: no reportar “faltó Tavily” en cada apertura.
        pass
    elif meta.get("missing_key"):
        data_gaps.append(
            "La búsqueda web no está configurada (falta TAVILY_API_KEY). "
            "La ficha muestra solo el contenido base curado."
        )
    elif meta.get("rate_limited"):
        data_gaps.append(
            "El proveedor de búsqueda limitó la tasa (429). "
            "Reintente para actualizar hechos desde la web."
        )
    elif meta.get("errors") and not (sources or []):
        data_gaps.append(
            "La búsqueda web no devolvió resultados en esta sesión. "
            "No inventamos comisiones ni requisitos."
        )

    if not curated_only and not updates.get("compensation"):
        data_gaps.append(
            "Sin cifras de compensación/ingresos atribuibles en la búsqueda "
            "de esta sesión. No se publican montos inventados."
        )

    sections_out: list[dict[str, Any]] = []
    for key, title in SECTION_ORDER:
        block = curated_sections.get(key) or {}
        body = str(block.get("body") or "").strip()
        attribution = str(block.get("attribution") or "curated")
        search_notes: list[dict[str, str]] = []

        if key == "requirements":
            search_notes = list(updates.get("requirements") or [])
        elif key == "income_potential":
            search_notes = list(updates.get("compensation") or [])
        elif key == "what_is":
            search_notes = list(updates.get("official") or [])[:2]

        sections_out.append(
            {
                "id": key,
                "title": title,
                "body": body,
                "attribution": attribution,
                "search_updates": search_notes,
                # Soft-tone does NOT apply to risks — UI may flag this.
                "honest_risks": key == "risks",
                "embed": None,
            }
        )

    # YouTube at top of "Qué es"
    media = plugin.get("media") or {}
    yt_id = str(media.get("what_is_youtube_id") or "").strip()
    if yt_id:
        for sec in sections_out:
            if sec["id"] == "what_is":
                sec["embed"] = {
                    "type": "youtube",
                    "video_id": yt_id,
                    "url": str(media.get("what_is_youtube_url") or "")
                    or f"https://youtu.be/{yt_id}",
                }
                break

    sponsorship = plugin.get("sponsorship") or {}
    curated_sources = list(curated.get("sources") or [])
    session_sources = [
        {
            "purpose": s.get("purpose"),
            "title": s.get("title"),
            "url": s.get("url"),
            "snippet": (s.get("snippet") or "")[:180],
            "attribution": "search",
        }
        for s in (sources or [])[:16]
    ]

    return {
        "ok": True,
        "pilot": False,
        "production": True,
        "id": plugin.get("id"),
        "title": plugin.get("title"),
        "tagline": plugin.get("tagline"),
        "category": plugin.get("category"),
        "status": "available",
        "curated_as_of": curated.get("as_of") or "",
        "sponsorship": {
            "url": sponsorship.get("url") or "",
            "cta_label": sponsorship.get("cta_label")
            or "Activar su franquicia (paquete manager)",
            "configured": bool(sponsorship.get("configured")),
            "source": sponsorship.get("source") or "none",
            "has_own": bool(sponsorship.get("has_own")),
        },
        "sections": sections_out,
        "sources": {
            "curated": curated_sources,
            "search": session_sources,
        },
        "data_gaps": data_gaps,
        "search_meta": meta,
    }
