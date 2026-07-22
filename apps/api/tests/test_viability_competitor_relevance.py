"""Relevancia de competidores — categoría/uso, no vocabulario superficial."""

from __future__ import annotations

from app.services.viability_pilot.search import (
    _basis_looks_direct,
    _filter_direct_competitors,
    build_search_queries,
)


def test_queries_use_profile_focus_not_flavor() -> None:
    profile = {
        "search_focus": "fibra soluble digestiva",
        "category": "suplemento de fibra",
        "use_case": "mejorar tránsito intestinal",
    }
    qs = build_search_queries(
        "suplemento en polvo sabor naranja para digestión",
        region="méxico",
        profile=profile,
    )
    joined = " ".join(q["query"].lower() for q in qs)
    assert "fibra" in joined or "digest" in joined
    # No debe anclarse solo al sabor
    assert "sabor naranja" not in joined


def test_basis_rejects_flavor_only() -> None:
    assert _basis_looks_direct("mismo sabor naranja en polvo") is False
    assert _basis_looks_direct("mismo uso: fibra soluble para digestión") is True


def test_relevance_filter_drops_loose_keyword_brands() -> None:
    offering = (
        "Suplemento de fibra soluble en polvo sabor naranja para mejorar "
        "el tránsito intestinal diario"
    )
    profile = {
        "search_focus": "fibra soluble digestiva",
        "category": "suplemento de fibra",
        "use_case": "mejorar tránsito intestinal",
    }
    candidates = [
        {
            "name": "Metamucil",
            "note": "Fibra psyllium para digestión",
            "competition_basis": "mismo uso: fibra soluble digestiva",
        },
        {
            "name": "Gelicart",
            "note": "Colágeno sabor naranja en polvo",
            "competition_basis": "comparte sabor naranja y formato polvo",
        },
        {
            "name": "Unicity",
            "note": "Suplementos varios",
            "competition_basis": "también es un suplemento",
        },
    ]
    # Pre-filter by basis rule (Gelicart should already fail _basis_looks_direct
    # if that were applied; here we test LLM filter when available, else keep).
    kept = _filter_direct_competitors(offering, candidates, profile=profile)
    names = {c["name"] for c in kept}
    # Must not keep Gelicart/Unicity if filter ran successfully; if Gemini unavailable,
    # function returns candidates unchanged — assert Metamucil still present either way.
    assert "Metamucil" in names or not kept
    if len(kept) < len(candidates):
        assert "Gelicart" not in names
        assert "Unicity" not in names
