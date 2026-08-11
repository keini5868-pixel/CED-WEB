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


def get_opportunity_detail(
    opportunity_id: str,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    plugin = get_plugin(opportunity_id, user_id=user_id)
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

    from app.config import get_settings

    live_search = bool(get_settings().opportunities_live_search)
    sources: list[dict[str, Any]] = []
    search_meta: dict[str, Any] = {
        "queries_run": 0,
        "result_rows": 0,
        "errors": [],
        "rate_limited": False,
        "missing_key": False,
        "sources": 0,
        "live_search": live_search,
        "curated_only": not live_search,
    }
    updates: dict[str, list[dict[str, str]]] = {}
    queries: list[dict[str, str]] = []

    if live_search:
        anchors = [
            str(a) for a in (plugin.get("search_anchors") or []) if str(a).strip()
        ]
        queries = build_opportunity_queries(anchors)
        sources, search_meta = run_opportunity_searches(queries)
        search_meta["live_search"] = True
        search_meta["curated_only"] = False
        updates = extract_search_updates(sources)
    else:
        # Ficha fija curada — sin Tavily / sin LLM por apertura.
        logger.info(
            "[OPPS] curated-only detail id=%s (OPPORTUNITIES_LIVE_SEARCH=false)",
            plugin.get("id"),
        )

    detail = build_opportunity_detail(
        plugin,
        search_updates=updates,
        search_meta=search_meta,
        sources=sources,
    )
    detail["queries"] = queries
    if user_id:
        try:
            from app.services.opportunities_pilot.fitline_action_plans import (
                get_active_plan,
            )

            plan = get_active_plan(user_id)
            detail["action_plan"] = plan
        except Exception:  # noqa: BLE001
            detail["action_plan"] = None
    logger.info(
        "[OPPS-PILOT] detail id=%s sources=%s gaps=%s sponsor=%s curated_only=%s",
        plugin.get("id"),
        len(sources),
        len(detail.get("data_gaps") or []),
        bool((plugin.get("sponsorship") or {}).get("configured")),
        not live_search,
    )
    return detail
