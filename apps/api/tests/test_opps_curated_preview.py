"""OPPS curated-only + preview persona."""

from __future__ import annotations

from app.services.opportunities_pilot.synthesize import build_opportunity_detail
from app.services.preview_persona import (
    bind_preview_as,
    is_cierre_partner_preview,
    reset_preview_as,
)


def test_build_detail_curated_only_no_search_gaps():
    plugin = {
        "id": "fitline-pm",
        "title": "PM",
        "tagline": "t",
        "category": "x",
        "curated": {
            "as_of": "2026-01",
            "sections": {
                "what_is": {"body": "Empresa", "attribution": "curated"},
                "risks": {"body": "MLM", "attribution": "curated"},
            },
            "sources": [],
        },
        "sponsorship": {"url": "https://x.test", "configured": True, "source": "default"},
        "media": {},
    }
    detail = build_opportunity_detail(
        plugin,
        search_updates={},
        search_meta={"curated_only": True, "live_search": False},
        sources=[],
    )
    assert detail["ok"] is True
    assert detail["data_gaps"] == []
    assert any(s["id"] == "what_is" for s in detail["sections"])


def test_cierre_preview_requires_admin(monkeypatch):
    token = bind_preview_as("cierre")
    try:
        monkeypatch.setattr(
            "app.services.preview_persona.user_may_use_preview",
            lambda _uid: False,
        )
        assert is_cierre_partner_preview("user-1") is False
        monkeypatch.setattr(
            "app.services.preview_persona.user_may_use_preview",
            lambda _uid: True,
        )
        assert is_cierre_partner_preview("admin-1") is True
    finally:
        reset_preview_as(token)


def test_get_opportunity_detail_skips_tavily(monkeypatch):
    from app.services.opportunities_pilot import service as svc

    called = {"search": 0}

    def boom(*_a, **_k):
        called["search"] += 1
        raise AssertionError("Tavily no debe llamarse en curated-only")

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: type("S", (), {"opportunities_live_search": False})(),
    )
    monkeypatch.setattr(svc, "run_opportunity_searches", boom)
    monkeypatch.setattr(
        svc,
        "get_plugin",
        lambda *_a, **_k: {
            "id": "fitline-pm-international",
            "title": "PM",
            "tagline": "",
            "category": "franchise",
            "status": "available",
            "search_anchors": ["PM International"],
            "curated": {"as_of": "2026", "sections": {}, "sources": []},
            "sponsorship": {},
            "media": {},
        },
    )
    out = svc.get_opportunity_detail("fitline-pm-international", user_id=None)
    assert out["ok"] is True
    assert called["search"] == 0
    assert out.get("search_meta", {}).get("curated_only") is True
