"""Tests — HUD carousel y CORS producción."""

from __future__ import annotations

from unittest.mock import patch

from app.config import Settings


def test_cors_includes_cedweb_production_origin():
    settings = Settings(cors_origins="http://localhost:3000", web_public_url="")
    origins = settings.cors_origin_list()
    assert "https://cedweb-production.up.railway.app" in origins
    assert "https://ced-web-production.up.railway.app" in origins


def test_hud_carousel_returns_200_on_build_error():
    from fastapi.testclient import TestClient

    from app.deps.auth import require_user_id
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: "user-test"
    client = TestClient(app)

    with patch("app.routers.hud.build_carousel_snapshot", side_effect=RuntimeError("db down")):
        res = client.get(
            "/v1/hud/carousel",
            headers={"Authorization": "Bearer test-token"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body.get("cards") == []
    assert body.get("error") == "carousel_unavailable"
