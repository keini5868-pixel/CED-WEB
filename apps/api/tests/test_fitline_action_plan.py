"""Tests — sponsor URL resolve + action plan helpers."""

from __future__ import annotations

from app.services.opportunities_pilot.fitline_action_plans import (
    build_plan_content_from_voice,
    format_plan_spoken,
)
from app.services.opportunities_pilot.fitline_sponsor import (
    normalize_sponsor_url,
    resolve_sponsor_url,
)


def test_normalize_sponsor_url():
    assert normalize_sponsor_url("https://example.com/join") == "https://example.com/join"
    assert normalize_sponsor_url("example.com/x").startswith("https://")
    assert normalize_sponsor_url("not a url") == ""
    assert normalize_sponsor_url("") == ""


def test_resolve_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(
        "app.services.opportunities_pilot.fitline_sponsor.get_user_sponsor_url",
        lambda _uid: "",
    )
    monkeypatch.setattr(
        "app.services.opportunities_pilot.fitline_sponsor.default_sponsor_url",
        lambda: "https://default.example/join",
    )
    out = resolve_sponsor_url("user-1")
    assert out["url"] == "https://default.example/join"
    assert out["source"] == "default"
    assert out["configured"] is True


def test_resolve_prefers_user_link(monkeypatch):
    monkeypatch.setattr(
        "app.services.opportunities_pilot.fitline_sponsor.get_user_sponsor_url",
        lambda _uid: "https://mine.example/join",
    )
    monkeypatch.setattr(
        "app.services.opportunities_pilot.fitline_sponsor.default_sponsor_url",
        lambda: "https://default.example/join",
    )
    out = resolve_sponsor_url("user-1")
    assert out["url"] == "https://mine.example/join"
    assert out["source"] == "user"
    assert out["has_own"] is True


def test_build_plan_content_uses_franquicia_focus():
    content = build_plan_content_from_voice(
        metas=["10 clientes"],
        pasos=["Probar Optimal-Set", "Pitch 30s"],
        horizonte="30 días",
    )
    assert content["franchise_focus"] == "FitLine / PM International"
    assert content["terminology"] == "franquicia"
    assert content["goals"] == ["10 clientes"]
    assert len(content["steps"]) == 2


def test_format_plan_spoken_empty():
    text = format_plan_spoken(None)
    assert "franquicia" in text.lower() or "plan" in text.lower()


def test_voice_tools_include_franchise_plan():
    from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

    names = {t.get("name") for t in OPENAI_REALTIME_TOOLS}
    assert "guardar_plan_crecimiento_franquicia" in names
    assert "abrir_oportunidades_fitline" in names
    assert "actualizar_enlace_patrocinio_fitline" in names


def test_sales_closer_mentions_franchise_bridge():
    from app.services.opportunities_pilot.fitline_knowledge import (
        fitline_sales_closer_overlay,
    )

    overlay = fitline_sales_closer_overlay()
    assert "franquicia" in overlay.lower()
    assert "guardar_plan_crecimiento_franquicia" in overlay or "PLAN DE FRANQUICIA" in overlay
