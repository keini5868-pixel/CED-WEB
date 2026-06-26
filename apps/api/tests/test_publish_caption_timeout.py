"""Tests — caption literal + timeout publicación."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from app.services.publish_text import validate_caption
from app.services.voice_tool_executor import PUBLISH_TIMEOUT_SEC, execute_voice_tool


def test_caption_rejects_ui_labels_like_subir_imagen():
    ok, reason = validate_caption("Subir imagen")
    assert ok is False
    assert "ui" in reason.lower()

    ok2, reason2 = validate_caption("📷 Subir imagen a CED")
    assert ok2 is False
    assert "ui" in reason2.lower()


def test_publish_requires_explicit_user_confirmation():
    from app.services.retell_custom_llm import resolve_meta_publish_request

    class Utterance:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content

    no_confirm = resolve_meta_publish_request(
        "Necesito publicar en Facebook con esa imagen, el mensaje será 'El sistema CED ha llegado'",
        [],
    )
    assert no_confirm is None

    transcript = [
        Utterance(
            "user",
            "publicar en facebook, el mensaje será El sistema CED ha llegado",
        ),
        Utterance("agent", "Voy a publicar: El sistema CED ha llegado. ¿Confirmo?"),
        Utterance("user", "sí envía"),
    ]
    confirmed = resolve_meta_publish_request("sí envía", transcript)
    assert confirmed is not None
    assert confirmed["platform"] == "facebook"
    assert "CED" in confirmed["caption"]


def test_resolve_image_finds_recent_upload():
    from app.services.publish_image_context import (
        clear_session_image,
        register_voice_session_image,
        resolve_image_for_publishing,
    )

    uid = "test-user-resolve-img"
    clear_session_image(uid)
    register_voice_session_image(uid, "https://cdn.example.com/voice-upload.png", filename="t.png")
    result = resolve_image_for_publishing(uid, None, use_last_uploaded_image=True)
    assert result["ok"] is True
    assert "voice-upload.png" in str(result.get("url") or "")
    clear_session_image(uid)


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
