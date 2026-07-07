"""Voz — autoridad de herramientas y contexto Meta en system prompt."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services.gemini_voice_tools import build_gemini_voice_tools
from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS
from app.services.voice_llm_common import build_voice_system
from app.services.voice_tool_executor import execute_voice_tool


def test_voice_tools_include_consultar_redes():
    names = {str(t.get("name")) for t in OPENAI_REALTIME_TOOLS}
    gemini = {
        decl.name
        for decl in (build_gemini_voice_tools().function_declarations or [])
        if decl.name
    }
    assert "consultar_redes_conectadas" in names
    assert "consultar_redes_conectadas" in gemini


def test_build_voice_system_includes_extras():
    with patch(
        "app.services.cognitive_router.build_voice_system_extras",
        return_value="META_CONECTADO_TEST",
    ):
        system = build_voice_system("user-1", "hola", lightweight=False)
    assert "META_CONECTADO_TEST" in system


def test_consultar_redes_conectadas_connected():
    async def run():
        with patch(
            "app.services.supabase_db.get_meta_connection",
            return_value={"access_token": "tok", "ig_username": "mi_negocio"},
        ):
            return await execute_voice_tool("consultar_redes_conectadas", "user-1", {})

    result = asyncio.run(run())
    assert result.get("ok") is True
    assert "mi_negocio" in str(result.get("spoken") or "")


def test_generate_image_with_reference_uses_session_image():
    async def run():
        with (
            patch(
                "app.services.voice_tool_executor._load_reference_image_bytes",
                return_value=(b"\xff\xd8\xff" + b"x" * 600, "image/jpeg"),
            ),
            patch(
                "app.services.image_reference_generator.generate_image_with_reference",
                return_value={"ok": True, "url": "https://cdn.example/img.jpg"},
            ),
            patch("app.services.voice_tool_executor.vcs.push_tool_event"),
        ):
            return await execute_voice_tool(
                "generate_image_with_reference",
                "user-1",
                {"prompt": "versión minimalista", "style_mode": "variation"},
            )

    result = asyncio.run(run())
    assert result.get("ok") is True
    assert "generada" in str(result.get("spoken") or "").lower()


def test_generate_image_with_reference_requires_reference():
    async def run():
        with patch(
            "app.services.voice_tool_executor._load_reference_image_bytes",
            return_value=None,
        ):
            return await execute_voice_tool(
                "generate_image_with_reference",
                "user-1",
                {"prompt": "cambia el fondo", "style_mode": "edit"},
            )

    result = asyncio.run(run())
    assert result.get("ok") is False
    assert result.get("error") == "missing_reference_image"
