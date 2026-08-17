"""Orquestación Análisis de Tendencia — piloto aislado."""

from __future__ import annotations

import logging
from typing import Any

from app.services.trends_pilot.profile import build_industry_profile
from app.services.trends_pilot.search import (
    build_trends_queries,
    extract_trend_facts,
    run_trends_searches,
)
from app.services.trends_pilot.synthesize import build_trends_report

logger = logging.getLogger(__name__)


def analyze_trends(
    *,
    description: str,
    region: str | None = None,
) -> dict[str, Any]:
    text = (description or "").strip()
    if len(text) < 8:
        return {
            "ok": False,
            "error": "missing_description",
            "message": "Describa su rubro o industria para el Análisis de Tendencia.",
            "spoken": "Señor, indíqueme su rubro o industria para el Análisis de Tendencia.",
            "pilot": True,
        }

    profile = build_industry_profile(text)
    queries = build_trends_queries(
        profile.get("anchor") or text,
        region=region,
        category=profile.get("category") or None,
        product_kind=profile.get("product_kind") or None,
    )
    sources, search_meta = run_trends_searches(queries)
    facts = extract_trend_facts(sources, profile=profile)
    report = build_trends_report(
        description=text,
        profile=profile,
        facts=facts,
        sources=sources,
        region=region,
        search_meta=search_meta,
    )
    report["ok"] = True
    report["queries"] = queries
    logger.info(
        "[TRENDS-PILOT] ok sources=%s trending=%s needs=%s outlook=%s gaps=%s anchor=%s",
        len(sources),
        len(report.get("trending_now") or []),
        len(report.get("consumer_needs") or []),
        (report.get("outlook_6m") or {}).get("attribution"),
        len(report.get("data_gaps") or []),
        (profile.get("anchor") or "")[:80],
    )
    return report
