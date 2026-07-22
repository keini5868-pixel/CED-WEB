"""Intents y ancla nominal — módulo Tendencias piloto."""

from __future__ import annotations

from app.services.trends_pilot.intents import is_trends_module_intent
from app.services.trends_pilot.profile import (
    build_industry_profile,
    extract_named_anchors,
    infer_product_kind,
)
from app.services.trends_pilot.search import (
    build_trends_queries,
    extract_trend_facts,
    source_matches_category,
)
from app.services.viability_pilot.intents import is_viability_module_intent


def test_trends_triggers() -> None:
    assert is_trends_module_intent("qué está trending en cafeterías de especialidad")
    assert is_trends_module_intent("tendencias de mi rubro de marketing digital")
    assert is_trends_module_intent("outlook a 6 meses del mercado de suplementos")


def test_trends_does_not_steal_viability() -> None:
    text = "Analiza la viabilidad de mi cafetería"
    assert is_viability_module_intent(text) is True
    assert is_trends_module_intent(text) is False


def test_named_anchor_not_generalized_in_queries() -> None:
    text = "vendo suplementos FitLine Basics y quiero tendencias del nicho"
    names = extract_named_anchors(text)
    assert any("fitline" in n.lower() for n in names)
    profile = build_industry_profile(text)
    assert "fitline" in (profile.get("anchor") or "").lower()
    qs = build_trends_queries(
        profile["anchor"],
        region="Estados Unidos",
        category=profile.get("category"),
        product_kind=profile.get("product_kind"),
    )
    joined = " ".join(q["query"] for q in qs).lower()
    assert "fitline" in joined


def test_goku_figures_inferred_physical() -> None:
    text = "figuras de goku en ultra instinto"
    assert infer_product_kind(text) == "physical_good"
    qs = build_trends_queries(
        text,
        category="coleccionables / action figures",
        product_kind="physical_good",
    )
    joined = " ".join(q["query"] for q in qs).lower()
    assert "collect" in joined or "figura" in joined or "physical" in joined
    assert "-crypto" in joined


def test_outlook_rejects_crypto_when_physical_collectible() -> None:
    profile = {
        "anchor": "figuras de goku en ultra instinto",
        "category": "coleccionables anime / action figures",
        "product_kind": "physical_good",
    }
    crypto_snip = (
        "GOKU crypto token price prediction: podría alcanzar hasta "
        "$0.00035136834 por 2026 según analistas de mercado."
    )
    figure_snip = (
        "Dragon Ball Ultra Instinct figures demand remains strong among "
        "collectors through 2026 with new retail releases on Amazon and Walmart."
    )
    assert source_matches_category(
        title="GOKU Price Prediction",
        snippet=crypto_snip,
        url="https://example.com/goku-crypto",
        profile=profile,
    ) is False
    assert source_matches_category(
        title="Anime collectibles market",
        snippet=figure_snip,
        url="https://example.com/figures",
        profile=profile,
    ) is True

    facts = extract_trend_facts(
        [
            {
                "purpose": "outlook_6m",
                "snippet": crypto_snip,
                "title": "GOKU Price Prediction",
                "url": "https://example.com/goku-crypto",
                "query": "goku forecast",
            },
            {
                "purpose": "outlook_6m",
                "snippet": figure_snip,
                "title": "Anime collectibles market",
                "url": "https://example.com/figures",
                "query": "goku figures outlook",
            },
        ],
        profile=profile,
    )
    texts = " ".join(f["text"] for f in facts["outlook_6m"]).lower()
    assert "0.000351" not in texts
    assert "collectors" in texts or "figures" in texts
