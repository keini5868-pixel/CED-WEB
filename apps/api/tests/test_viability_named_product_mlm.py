"""Nombre propio + canal MLM como ancla de búsqueda."""

from __future__ import annotations

from app.services.viability_pilot.offering_profile import (
    extract_named_products_from_text,
    summarize_offering_profile,
)
from app.services.viability_pilot.search import build_search_queries


def test_extract_fitline_name_from_user_prompt() -> None:
    text = (
        "Analízame el mercado de este producto llamado FitLine Basics, "
        "precios y estrategia de venta para Estados Unidos"
    )
    names = extract_named_products_from_text(text)
    assert names
    assert any("fitline" in n.lower() and "basics" in n.lower() for n in names)


def test_fitline_queries_anchor_on_product_name_and_mlm() -> None:
    profile = {
        "product_name": "FitLine Basics",
        "brand": "PM International",
        "search_focus": "FitLine Basics PM International fibra probióticos",
        "category": "fibra + probióticos MLM",
        "use_case": "suplemento wellness venta directa",
        "channel": "mlm_direct",
    }
    qs = build_search_queries(
        "producto llamado FitLine Basics para Estados Unidos",
        region="Estados Unidos",
        profile=profile,
    )
    joined = " ".join(q["query"] for q in qs).lower()
    assert "fitline basics" in joined
    assert "mlm" in joined or "direct selling" in joined or "directa" in joined
    # Must not be only generic supermarket fiber query
    assert not (
        "metamucil" in joined and "fitline" not in joined
    )


def test_profile_keeps_named_product_over_generic_category() -> None:
    text = (
        "Analízame el mercado de este producto llamado FitLine Basics, "
        "precios y estrategia de venta para Estados Unidos"
    )
    image = (
        "Suplemento en polvo de fibra con probióticos en empaque azul. "
        "Parece un producto de nutrición genérico."
    )
    profile = summarize_offering_profile(
        f"TEXTO_USUARIO:\n{text}\n\nDESCRIPCION_IMAGEN:\n{image}",
        text_input=text,
        image_description=image,
    )
    assert "fitline" in (profile.get("product_name") or "").lower() or "fitline" in (
        profile.get("search_focus") or ""
    ).lower()
    # search_focus should lead with the named product
    focus = (profile.get("search_focus") or "").lower()
    assert focus.startswith("fitline") or "fitline basics" in focus
