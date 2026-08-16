"""Historial de imágenes generadas — GET /v1/images/history."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app

SAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"


def test_image_history_endpoint_maps_public_url():
    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID
    rows = [
        {
            "id": "img-1",
            "prompt": "gato astronauta",
            "quality": "standard",
            "model": "gemini",
            "public_url": "/v1/media/publish/gato.png",
            "created_at": "2026-08-15T12:00:00Z",
        },
        {
            "id": "img-2",
            "prompt": "sin url",
            "quality": "standard",
            "model": "gemini",
            "public_url": "",
            "created_at": "2026-08-15T12:01:00Z",
        },
    ]
    with patch("app.services.supabase_db.list_generated_images", return_value=rows):
        client = TestClient(app)
        res = client.get(
            "/v1/images/history",
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    images = res.json()["images"]
    assert len(images) == 1
    assert images[0]["id"] == "img-1"
    assert images[0]["url"] == "/v1/media/publish/gato.png"
    assert images[0]["prompt"] == "gato astronauta"
    app.dependency_overrides.clear()
