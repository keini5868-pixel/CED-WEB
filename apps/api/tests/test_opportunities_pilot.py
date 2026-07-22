"""Intents de tono y catálogo — módulo Oportunidades piloto."""

from __future__ import annotations

from app.services.opportunities_pilot.catalog import catalog_summaries, get_plugin
from app.services.opportunities_pilot.plugins.fitline_pm import fitline_pm_plugin
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
    detail = build_opportunity_detail(plugin, search_updates={}, search_meta={}, sources=[])
    ids = [s["id"] for s in detail["sections"]]
    assert "affiliation" in ids
    assert "risks" in ids
    assert detail["sponsorship"]["cta_label"] == "Activar su negocio (paquete manager)"
