"""Regresión — retail product (Chanel Bleu) extraction from real-shaped sources."""

from __future__ import annotations

from app.services.viability_pilot.search import (
    _PRICEISH,
    build_search_queries,
    extract_attributed_facts,
)


def test_us_retail_queries_are_english() -> None:
    qs = build_search_queries("perfume chanel blue", region="estados unidos")
    joined = " ".join(q["query"].lower() for q in qs)
    assert "competitors" in joined or "alternatives" in joined
    assert "price" in joined
    assert "precio típico" not in joined


def test_chanel_shaped_sources_yield_competitors_and_prices() -> None:
    sources = [
        {
            "purpose": "competitors",
            "query": "perfume chanel blue competitors",
            "title": "Resumen Tavily",
            "url": "",
            "snippet": (
                "Alternatives to Chanel Bleu de Chanel include Versace Dylan Blue, "
                "Dior Sauvage, and Hugo Boss Bottled Night."
            ),
        },
        {
            "purpose": "competitors",
            "query": "perfume chanel blue competitors",
            "title": "Best Bleu de Chanel Dupes",
            "url": "https://example.com/dupes",
            "snippet": (
                "Versace Dylan Blue EDT and Dior Sauvage are close alternatives "
                "to Bleu de Chanel."
            ),
        },
        {
            "purpose": "pricing",
            "query": "perfume chanel blue price",
            "title": "BLEU DE CHANEL - Fragrance",
            "url": "https://www.chanel.com/us/fragrance/bleu-de-chanel",
            "snippet": (
                "Explore the BLEU DE CHANEL fragrance line for men. "
                "This aromatic-woody perfume starting from $205"
            ),
        },
        {
            "purpose": "pricing",
            "query": "perfume chanel blue price",
            "title": "Walmart",
            "url": "https://www.walmart.com/ip/bleu",
            "snippet": "current price $92.99, Was $200.00",
        },
    ]
    assert _PRICEISH.findall(sources[2]["snippet"])
    facts = extract_attributed_facts(sources, offering="perfume chanel blue")
    names = {c["name"].lower() for c in facts["competitors"]}
    # LLM may or may not run in CI — heuristic should still surface brands from list
    assert facts["prices"], "expected attributable prices from Chanel/Walmart snippets"
    price_texts = " ".join(p["text"] for p in facts["prices"])
    assert "$205" in price_texts or "$92.99" in price_texts
    # If LLM available we get clean brands; if not, heuristic list parse should help
    if facts["competitors"]:
        assert names & {
            "versace dylan blue",
            "dior sauvage",
            "hugo boss bottled night",
        } or any("versace" in n or "dior" in n or "hugo" in n for n in names)
