"""Orquestación del análisis de viabilidad — aislado del resto de CED."""

from __future__ import annotations

import logging
from typing import Any

from app.services.viability_pilot.extract import resolve_offering_text
from app.services.viability_pilot.search import (
    build_search_queries,
    extract_attributed_facts,
    run_targeted_searches,
)
from app.services.viability_pilot.synthesize import build_viability_report

logger = logging.getLogger(__name__)


def analyze_viability(
    *,
    description: str | None = None,
    image_b64: str | None = None,
    region: str | None = None,
    category_hint: str | None = None,
    polish: bool = True,
) -> dict[str, Any]:
    """Pipeline completo: extract → multi-search → facts → report."""
    resolved = resolve_offering_text(description=description, image_b64=image_b64)
    offering = resolved["offering"]
    if not offering or len(offering) < 8:
        return {
            "ok": False,
            "error": "missing_offering",
            "message": (
                "Necesito una descripción del producto/servicio, o una imagen/flyer, "
                "para analizar viabilidad."
            ),
            "spoken": (
                "Señor, descríbame el producto o servicio, o adjunte un flyer, "
                "para el análisis de viabilidad."
            ),
            "pilot": True,
        }

    queries = build_search_queries(
        offering,
        region=region,
        category_hint=category_hint,
    )
    sources, search_meta = run_targeted_searches(
        queries, offering=offering, region=region
    )
    facts = extract_attributed_facts(sources, offering=offering)
    report = build_viability_report(
        offering,
        facts,
        sources,
        region=region,
        polish=polish,
        search_meta=search_meta,
    )
    report["ok"] = True
    report["queries"] = queries
    report["search_meta"] = search_meta
    report["extraction"] = {
        "text_input": resolved["text_input"],
        "image_description": resolved["image_description"],
        "has_image": resolved["has_image"],
    }
    logger.info(
        "[VIABILITY-PILOT] ok sources=%s competitors=%s prices=%s gaps=%s meta=%s",
        len(sources),
        len(report.get("competitors") or []),
        len((report.get("pricing") or {}).get("findings") or []),
        len(report.get("data_gaps") or []),
        {
            "result_rows": search_meta.get("result_rows"),
            "errors": len(search_meta.get("errors") or []),
            "rate_limited": search_meta.get("rate_limited"),
            "fallback_used": search_meta.get("fallback_used"),
        },
    )
    return report


def format_report_for_voice(report: dict[str, Any]) -> str:
    """Texto hablable corto a partir del informe (Retell result string)."""
    if not report.get("ok"):
        return str(report.get("spoken") or report.get("message") or "No pude analizar la viabilidad.")
    spoken = str(report.get("spoken") or "").strip()
    if spoken:
        return spoken
    band = (report.get("likelihood") or {}).get("range") or "sin rango"
    comps = report.get("competitors") or []
    names = ", ".join(c.get("name", "") for c in comps[:3] if c.get("name"))
    gaps = report.get("data_gaps") or []
    parts = [f"Viabilidad orientativa: {band}."]
    if names:
        parts.append(f"Comparables: {names}.")
    else:
        parts.append("Sin suficientes competidores verificables en búsqueda.")
    if gaps:
        parts.append("Hay limitaciones de datos declaradas en el informe.")
    return " ".join(parts)
