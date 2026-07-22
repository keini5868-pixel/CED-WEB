"""Intents y ancla nominal — módulo Tendencias piloto."""

from __future__ import annotations

from app.services.trends_pilot.intents import is_trends_module_intent
from app.services.trends_pilot.profile import (
    build_industry_profile,
    extract_named_anchors,
)
from app.services.trends_pilot.search import build_trends_queries
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
    qs = build_trends_queries(profile["anchor"], region="Estados Unidos")
    joined = " ".join(q["query"] for q in qs).lower()
    assert "fitline" in joined
