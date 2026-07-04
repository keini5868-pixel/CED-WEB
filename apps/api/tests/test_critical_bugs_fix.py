"""Tests — fixes críticos post-v43 (saludo, cámara, publicación)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services.publish_image_context import (
    clear_session_image,
    register_text_chat_image_url,
    resolve_image_for_publishing,
)
from app.services.publish_text import validate_caption
from app.services.voice_greetings import _adapt_time_of_day, get_user_local_hour, get_user_timezone
from app.services.voice_tool_executor import execute_voice_tool


def test_greeting_uses_user_timezone():
    with patch("app.services.voice_greetings.get_user_timezone", return_value="America/New_York"):
        with patch("app.services.voice_greetings.datetime") as mock_dt:
            mock_dt.now.return_value = type("T", (), {"hour": 6})()
            assert get_user_local_hour("user-charlotte") == 6

    with patch("app.services.voice_greetings.datetime") as mock_dt:
        mock_dt.now.return_value = type("T", (), {"hour": 6})()
        morning = _adapt_time_of_day("Hola, señor. Sistemas listos.", tz_name="America/New_York")
        assert morning.startswith("Buenos días")

        mock_dt.now.return_value = type("T", (), {"hour": 4})()
        night_mexico = _adapt_time_of_day("Hola, señor. Sistemas listos.", tz_name="America/Mexico_City")
        assert night_mexico.startswith("Buenas noches")


def test_camera_returns_analysis_or_honest_error():
    async def run() -> dict:
        with patch(
            "app.services.voice_tool_executor._wait_vision_result",
            return_value=None,
        ):
            return await execute_voice_tool(
                "analyze_camera_frame",
                "user-cam-1",
                {"question": "¿Qué ves?"},
            )

    result = asyncio.run(run())
    assert result.get("ok") is False
    spoken = result.get("spoken", "").lower()
    assert "no pude" in spoken
    assert "capturar" in spoken or "procesar" in spoken


def test_publish_resolves_image_automatically():
    uid = "user-pub-auto"
    cid = "conv-pub-auto"
    clear_session_image(uid, cid)
    register_text_chat_image_url(uid, cid, "https://cdn.example.com/auto.jpg")

    resolved = resolve_image_for_publishing(uid, cid, use_last_uploaded_image=True)
    assert resolved["ok"] is True
    assert resolved["url"] == "https://cdn.example.com/auto.jpg"


def test_publish_rejects_dirty_caption():
    dirty = "sí dale envía la publicación visita Charlotte una ciudad que inspira dale envía"
    ok, reason = validate_caption(dirty)
    assert ok is False
    assert reason

    clean = "Visita Charlotte, una ciudad que inspira crecimiento y nuevas oportunidades."
    ok_clean, _ = validate_caption(clean)
    assert ok_clean is True


def test_get_user_timezone_defaults_to_charlotte_region():
    with patch("app.services.supabase_db.get_profile", return_value=None):
        assert get_user_timezone("user-no-profile") == "America/New_York"
