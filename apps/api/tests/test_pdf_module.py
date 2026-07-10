"""Tests — módulo PDF de voz."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.modules.pdf_module import PdfModule
from app.services.retell_llm_types import Utterance


def test_pdf_module_resolves_title_and_body_from_history():
    module = PdfModule()
    utterances = [
        Utterance(role="user", content="Analiza mi estrategia de marketing"),
        Utterance(
            role="agent",
            content=(
                "Estrategia recomendada:\n"
                "1. Contenido educativo diario.\n"
                "2. Reels de antes y después.\n"
                "3. Promoción de fin de semana."
            ),
        ),
    ]
    captured: dict = {}

    async def fake_tool(name, user_id, params):
        captured.update(params)
        return {
            "ok": True,
            "spoken": "PDF listo, señor. Título: Estrategia CED. Ya está en su historial.",
            "file_id": "abc123",
            "title": "Estrategia CED",
        }

    with patch(
        "app.modules.pdf_module.execute_voice_tool",
        new=AsyncMock(side_effect=fake_tool),
    ):
        result = asyncio.run(
            module.activate(
                "",
                user_id="u1",
                call_id="c1",
                user_text="Ponme esto en un PDF",
                utterances=utterances,
            )
        )

    assert result.ok is True
    assert captured.get("conversation_id") == "c1"
    assert captured.get("titulo")
    assert captured.get("titulo") != "Documento CED" or len(captured.get("contenido", "")) > 40
    assert captured.get("_pdf_fallback_texts")
    assert any(ev.get("type") == "pdf_created" for ev in result.tool_events)
    assert "historial" in result.spoken.lower()
