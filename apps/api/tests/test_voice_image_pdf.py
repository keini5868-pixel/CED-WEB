"""Tests — generación de imagen/PDF por voz (pipeline compartida + eventos UI)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.voice_tool_async import IMAGE_TOOL_TIMEOUT_SEC, tool_timeout_sec
from app.services.voice_tool_executor import execute_voice_tool


def test_image_and_pdf_tool_timeouts():
    assert tool_timeout_sec("generate_image") == IMAGE_TOOL_TIMEOUT_SEC
    assert tool_timeout_sec("generate_image") == 60.0
    assert tool_timeout_sec("generar_pdf") == 35.0


def test_voice_generate_image_uses_shared_pipeline_and_pushes_event():
    pushed: list[dict] = []

    def _push(user_id: str, event: dict) -> None:
        pushed.append({"user_id": user_id, **event})

    with (
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={
                "ok": True,
                "url": "https://cdn.example.com/cafe.png",
                "caption": "Café",
                "reply": "Listo",
            },
        ) as mock_gen,
        patch("app.services.voice_tool_executor.voice_access_state", return_value={"plan_id": "elite"}),
        patch("app.services.voice_tool_executor.vcs.push_tool_event", side_effect=_push),
    ):
        result = asyncio.run(
            execute_voice_tool(
                "generate_image",
                "user-voice-img",
                {"prompt": "un café al atardecer", "call_id": "call-1"},
            )
        )

    mock_gen.assert_called_once()
    kwargs = mock_gen.call_args.kwargs
    assert kwargs.get("allow_reference") is False
    assert kwargs.get("plan_id") == "elite"
    assert mock_gen.call_args.args[2] == "un café al atardecer"
    assert result["ok"] is True
    assert result["url"] == "https://cdn.example.com/cafe.png"
    assert "pantalla" in result["spoken"].lower()
    assert pushed and pushed[0]["type"] == "generated_image"
    assert pushed[0]["image_url"] == "https://cdn.example.com/cafe.png"


def test_voice_generate_image_no_event_on_failure():
    pushed: list[dict] = []

    with (
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={"ok": False, "error": "quota exceeded", "url": None, "reply": "quota"},
        ),
        patch("app.services.voice_tool_executor.voice_access_state", return_value={"plan_id": "elite"}),
        patch(
            "app.services.voice_tool_executor.vcs.push_tool_event",
            side_effect=lambda *a, **k: pushed.append(a),
        ),
    ):
        result = asyncio.run(
            execute_voice_tool("generate_image", "user-voice-img", {"prompt": "algo"})
        )

    assert result["ok"] is False
    assert "imagen" in result["spoken"].lower()
    assert not pushed


def test_voice_generate_image_requires_prompt():
    result = asyncio.run(execute_voice_tool("generate_image", "user-voice-img", {"prompt": ""}))
    assert result["ok"] is False
    assert "indique" in result["spoken"].lower() or "imagen" in result["spoken"].lower()


def test_voice_generar_pdf_pushes_event_on_success():
    pushed: list[dict] = []
    artifact = SimpleNamespace(file_id="pdf-abc", title="Lista de tareas")

    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(SimpleNamespace(pdf_reports=True), None, None),
        ),
        patch(
            "app.services.voice_tool_executor.store_pdf_with_timeout",
            return_value=artifact,
        ),
        patch(
            "app.services.voice_tool_executor.vcs.push_tool_event",
            side_effect=lambda uid, ev: pushed.append(ev),
        ),
    ):
        result = asyncio.run(
            execute_voice_tool(
                "generar_pdf",
                "user-voice-pdf",
                {
                    "titulo": "Lista de tareas",
                    "contenido": "1. Comprar café\n2. Revisar informes",
                    "call_id": "call-pdf",
                },
            )
        )

    assert result["ok"] is True
    assert "PDF listo" in result["spoken"]
    assert result["file_id"] == "pdf-abc"
    assert pushed and pushed[0]["type"] == "pdf_created"
    assert pushed[0]["file_id"] == "pdf-abc"
