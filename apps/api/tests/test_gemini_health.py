"""Ping de Gemini no debe marcar ALERTA por thought tokens."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.integrations import _gemini_response_text, check_google
from app.services.hud_health import build_detailed_health, health_card_lines


def test_gemini_response_text_prefers_response_text() -> None:
    assert _gemini_response_text(SimpleNamespace(text="  ok  ", candidates=[])) == "ok"


def test_gemini_response_text_falls_back_to_parts() -> None:
    part = SimpleNamespace(text="pong")
    cand = SimpleNamespace(content=SimpleNamespace(parts=[part]))
    resp = SimpleNamespace(text="", candidates=[cand])
    assert _gemini_response_text(resp) == "pong"


def test_check_google_missing_key() -> None:
    settings = SimpleNamespace(google_api_key="  ")
    with patch("app.services.integrations.get_settings", return_value=settings):
        out = check_google()
    assert out["ok"] is False
    assert out["error"] == "missing_google_api_key"


def test_check_google_ok_on_text() -> None:
    settings = SimpleNamespace(google_api_key="gk")
    fake_types = MagicMock()
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = SimpleNamespace(
        text="ok",
        candidates=[],
    )
    fake_genai = MagicMock()
    fake_genai.Client.return_value = fake_client
    with (
        patch("app.services.integrations.get_settings", return_value=settings),
        patch.dict("sys.modules", {"google": MagicMock(genai=fake_genai), "google.genai": fake_genai}),
    ):
        fake_genai.types = fake_types
        # from google import genai; from google.genai import types
        import sys

        sys.modules["google.genai"].types = fake_types
        out = check_google()
    assert out["ok"] is True
    assert out["model"] == "gemini-2.5-flash"


def test_check_google_ok_when_candidates_without_text() -> None:
    """Regresión HUD: 2.5-pro + 8 tokens → texto vacío, clave válida."""
    settings = SimpleNamespace(google_api_key="gk")
    fake_types = MagicMock()
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = SimpleNamespace(
        text="",
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))],
    )
    fake_genai = MagicMock()
    fake_genai.Client.return_value = fake_client
    fake_genai.types = fake_types
    with (
        patch("app.services.integrations.get_settings", return_value=settings),
        patch.dict(
            "sys.modules",
            {"google": MagicMock(genai=fake_genai), "google.genai": fake_genai},
        ),
    ):
        out = check_google()
    assert out["ok"] is True
    assert out.get("note") == "empty_text_but_candidates"


def test_hud_health_not_alerta_when_gemini_ok() -> None:
    gemini_ok = {"ok": True, "model": "gemini-2.5-flash"}
    db_ok = {"ok": True}
    stripe_ok = {"ok": True}
    with (
        patch("app.services.hud_health.check_gemini", return_value=gemini_ok),
        patch("app.services.hud_health.check_supabase", return_value=db_ok),
        patch("app.services.hud_health.check_supabase_auth", return_value=db_ok),
        patch("app.services.hud_health.check_stripe", return_value=stripe_ok),
    ):
        health = build_detailed_health()
    assert health["ok"] is True
    lines = health_card_lines(health)
    assert "ALERTA" not in lines[0]
    assert "OK" in lines[0]
