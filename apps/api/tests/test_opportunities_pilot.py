"""Intents de tono y catálogo — módulo Oportunidades piloto."""

from __future__ import annotations

from app.services.opportunities_pilot.catalog import catalog_summaries, get_plugin
from app.services.opportunities_pilot.plugins.fitline_pm import fitline_pm_plugin
from app.services.opportunities_pilot.search import (
    _normalize_anchors,
    _row_ok,
    build_opportunity_queries,
    is_promotional_or_testimonial,
)
from app.services.opportunities_pilot.synthesize import build_opportunity_detail

_SOFT_BANNED = ("multinivel", "mlm", "red de mercadeo", "afiliados")


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
    assert detail["sponsorship"]["cta_label"] == "Activar su negocio (paquete manager)"


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
