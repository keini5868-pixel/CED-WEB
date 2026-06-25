"""Tests — caption literal + timeout publicación."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from app.services.publish_text import validate_caption
from app.services.voice_tool_executor import PUBLISH_TIMEOUT_SEC, execute_voice_tool


def test_caption_rejects_publish_command_literal():
    ok, reason = validate_caption("Publica tus características en Facebook")
    assert ok is False
    assert "instrucción" in reason.lower()

    ok2, _ = validate_caption("Publica un mensaje motivacional")
    assert ok2 is False

    ok3, _ = validate_caption("Visita Charlotte, una ciudad que inspira crecimiento.")
    assert ok3 is True


def test_publish_facebook_timeout_returns_honest_error():
    def slow_publish(*_a, **_k):
        time.sleep(PUBLISH_TIMEOUT_SEC + 2)
        return {"ok": True, "spoken": "Publicado"}

    async def run() -> dict:
        with patch("app.services.voice_tool_executor.publish_facebook", slow_publish):
            return await execute_voice_tool(
                "publicar_facebook",
                "user-pub-timeout",
                {"mensaje": "CED potencia tu negocio digital con voz e IA."},
            )

    result = asyncio.run(run())
    assert result.get("ok") is False
    assert result.get("error") == "timeout"
    assert "tardando" in result.get("spoken", "").lower()


def test_publish_instagram_timeout_returns_honest_error():
    def slow_publish(*_a, **_k):
        time.sleep(PUBLISH_TIMEOUT_SEC + 2)
        return {"ok": True, "spoken": "Publicado"}

    async def run() -> dict:
        with (
            patch("app.services.voice_tool_executor.publish_instagram", slow_publish),
            patch(
                "app.services.voice_tool_executor._resolve_image_for_publishing",
                return_value={"ok": True, "url": "https://cdn.example.com/img.jpg"},
            ),
        ):
            return await execute_voice_tool(
                "publicar_instagram",
                "user-pub-timeout-ig",
                {"caption": "Visita Charlotte, una ciudad que inspira crecimiento."},
            )

    result = asyncio.run(run())
    assert result.get("ok") is False
    assert result.get("error") == "timeout"
    assert "tardando" in result.get("spoken", "").lower()
