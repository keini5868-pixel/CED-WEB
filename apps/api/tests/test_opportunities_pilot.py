"""Intents de tono, catálogo y gate — módulo Oportunidades (producción)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.opportunities_pilot.catalog import catalog_summaries, get_plugin
from app.services.opportunities_pilot.gate import (
    opportunities_module_enabled,
    require_opportunities_module_enabled,
)
from app.services.opportunities_pilot.plugins.fitline_pm import fitline_pm_plugin
from app.services.opportunities_pilot.search import (
    _normalize_anchors,
    _row_ok,
    build_opportunity_queries,
    is_promotional_or_testimonial,
)
from app.services.opportunities_pilot.synthesize import build_opportunity_detail

_SOFT_BANNED = ("multinivel", "mlm", "red de mercadeo", "afiliados")


def test_gate_enabled_by_default() -> None:
    with patch(
        "app.services.opportunities_pilot.gate.get_settings",
    ) as mock_settings:
        mock_settings.return_value.opportunities_module_enabled = True
        assert opportunities_module_enabled() is True
        require_opportunities_module_enabled()  # no raise


def test_gate_kill_switch_returns_404() -> None:
    with patch(
        "app.services.opportunities_pilot.gate.get_settings",
    ) as mock_settings:
        mock_settings.return_value.opportunities_module_enabled = False
        assert opportunities_module_enabled() is False
        with pytest.raises(HTTPException) as exc:
            require_opportunities_module_enabled()
        assert exc.value.status_code == 404


def test_detail_marks_production_not_pilot() -> None:
    plugin = fitline_pm_plugin()
    detail = build_opportunity_detail(
        plugin, search_updates={}, search_meta={}, sources=[]
    )
    assert detail["pilot"] is False
    assert detail["production"] is True


def test_catalog_only_fitline() -> None:
    rows = catalog_summaries()
    assert len(rows) == 1
    assert rows[0]["id"] == "fitline_pm"
    assert rows[0]["status"] == "available"


def test_unknown_opportunity_missing() -> None:
    assert get_plugin("crypto_goku") is None


def test_soft_tone_except_risks() -> None:
    plugin = fitline_pm_plugin()
    sections = (plugin.get("curated") or {}).get("sections") or {}
    for key, block in sections.items():
        body = (block.get("body") or "").lower()
        if key == "risks":
            assert "venta directa" in body
            assert "comisiones por red" in body or "comisiones" in body
            assert "no está garantizado" in body or "no garantizado" in body
            continue
        for banned in _SOFT_BANNED:
            assert banned not in body, f"{key} contains {banned}"


def test_detail_includes_affiliation_and_cta() -> None:
    plugin = fitline_pm_plugin()
    detail = build_opportunity_detail(
        plugin, search_updates={}, search_meta={}, sources=[]
    )
    ids = [s["id"] for s in detail["sections"]]
    assert "affiliation" in ids
    assert "risks" in ids
    assert "company_history" in ids
    assert "products" in ids
    assert detail["sponsorship"]["cta_label"] == "Activar su negocio (paquete manager)"


def test_enriched_fitline_has_official_facts() -> None:
    plugin = fitline_pm_plugin()
    sections = (plugin.get("curated") or {}).get("sections") or {}
    history = (sections.get("company_history") or {}).get("body") or ""
    science = (sections.get("science_credibility") or {}).get("body") or ""
    products = (sections.get("products") or {}).get("body") or ""
    req = (sections.get("requirements") or {}).get("body") or ""
    income = (sections.get("income_potential") or {}).get("body") or ""
    prospect = (sections.get("prospecting") or {}).get("body") or ""
    assert "1993" in history
    assert "Speyer" in history or "Alemania" in history
    assert "Schengen" in history or "Luxemburgo" in history
    assert "40" in history
    assert "3.22" in history or "mil millones" in history
    assert "NTC" in science or "Nutrient Transport" in science
    assert "TÜV" in science or "TUV" in science.upper()
    assert "PowerCocktail" in products and "$119.48" in products
    assert "Activize" in products and "Restorate" in products
    assert "Manager Quickstart" in req and "$596" in req
    assert "Teampartner Start" in req
    assert "Partner Area" in req or "NO invent" in req
    assert "Income Plan" in income
    assert "Team Partner" in income
    assert "PAS" in prospect or "hook" in prospect.lower()
    sources = (plugin.get("curated") or {}).get("sources") or []
    urls = " ".join(str(s.get("url") or "") for s in sources)
    assert "pm-international.com" in urls
    assert "fitline.com" in urls
    assert "pmebusiness.com" in urls


def test_what_is_embeds_youtube() -> None:
    plugin = fitline_pm_plugin()
    detail = build_opportunity_detail(
        plugin, search_updates={}, search_meta={}, sources=[]
    )
    what = next(s for s in detail["sections"] if s["id"] == "what_is")
    assert what["embed"]["type"] == "youtube"
    assert what["embed"]["video_id"] == "2kGPd94Ou4o"


def test_queries_never_use_bare_pm() -> None:
    qs = build_opportunity_queries(["PM", "FitLine"])
    joined = " ".join(q["query"] for q in qs)
    assert "PM International" in joined
    assert "FitLine" in joined
    for q in qs:
        assert "PM International" in q["query"] or "FitLine" in q["query"]
        assert '"PM"' not in q["query"]


def test_normalize_expands_bare_pm() -> None:
    out = _normalize_anchors(["PM", "negocio"])
    assert any(x == "PM International" for x in out)


def test_drop_pm_wikipedia_noise() -> None:
    assert (
        _row_ok(
            "PM - Wikipedia",
            "PM may refer to: ante meridiem, prime minister, or other acronyms.",
            "https://en.wikipedia.org/wiki/PM",
        )
        is False
    )
    assert (
        _row_ok(
            "PM-International FitLine",
            "PM International manufactures FitLine nutrition products worldwide.",
            "https://www.pm-international.com/",
        )
        is True
    )


def test_drop_distributor_testimonial() -> None:
    claim = (
        "we have the highest compensation plan pay out there at 62%. "
        "Truly a historic moment for PM-International!"
    )
    assert is_promotional_or_testimonial("Distributor story", claim) is True
    assert (
        _row_ok(
            "Distributor story",
            claim,
            "https://example.com/blog/my-fitline-story",
        )
        is False
    )
    assert (
        is_promotional_or_testimonial(
            "Facebook",
            "Hello, my name is Kevin and I am building FitLine with PM International",
        )
        is True
    )
