"""Orquestación Oportunidades — módulo en producción (aislado del chat/voz)."""

from __future__ import annotations

import logging
from typing import Any

from app.services.opportunities_pilot.catalog import catalog_summaries, get_plugin
from app.services.opportunities_pilot.search import (
    build_opportunity_queries,
    extract_search_updates,
    run_opportunity_searches,
)
from app.services.opportunities_pilot.synthesize import build_opportunity_detail

logger = logging.getLogger(__name__)


def list_opportunity_catalog() -> dict[str, Any]:
    return {
        "ok": True,
        "pilot": False,
        "production": True,
        "opportunities": catalog_summaries(),
    }


def get_opportunity_detail(opportunity_id: str) -> dict[str, Any]:
    plugin = get_plugin(opportunity_id)
    if not plugin:
        return {
            "ok": False,
            "error": "not_found",
            "message": (
                "Esa oportunidad aún no está integrada en CED. "
                "Las disponibles aparecen en el catálogo del módulo."
            ),
            "pilot": False,
            "production": True,
        }

    anchors = [str(a) for a in (plugin.get("search_anchors") or []) if str(a).strip()]
    queries = build_opportunity_queries(anchors)
    sources, search_meta = run_opportunity_searches(queries)
    updates = extract_search_updates(sources)
    detail = build_opportunity_detail(
        plugin,
        search_updates=updates,
        search_meta=search_meta,
        sources=sources,
    )
    detail["queries"] = queries
    logger.info(
        "[OPPS-PILOT] detail id=%s sources=%s gaps=%s sponsor=%s",
        plugin.get("id"),
        len(sources),
        len(detail.get("data_gaps") or []),
        bool((plugin.get("sponsorship") or {}).get("configured")),
    )
    return detail
