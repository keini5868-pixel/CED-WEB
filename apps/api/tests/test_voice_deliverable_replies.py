"""Tests — entregables completos compartidos (chat + voz)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.deliverable_replies import (
    is_deliverable_request,
    is_incomplete_deliverable,
    merge_deliverable_continuation,
)
from app.services.gemini_voice_llm import GeminiVoiceLlm
from app.services.voice_llm_common import voice_generation_limits
from app.services.voice_spoken import VOICE_DELIVERABLE_MAX_CHARS, voice_spoken_limit


def test_voice_deliverable_request_gets_higher_token_budget():
    text = "crea una estrategia semanal para lanzar CED"
    max_tokens, timeout = voice_generation_limits(text)
    assert max_tokens >= 3200
    assert timeout >= 28.0


def test_voice_spoken_limit_for_deliverable():
    text = "elabora un plan semanal de marketing"
    assert voice_spoken_limit(text) == VOICE_DELIVERABLE_MAX_CHARS


def test_is_incomplete_deliverable_intro_only_voice():
    user = "crea una estrategia semanal y a que publico dirigirla"
    reply = (
        "Entendido, señor. Aquí le presento una estrategia semanal enfocada "
        "en las soluciones más relevantes de CED, dirigida a un público"
    )
    assert is_incomplete_deliverable(reply, user) is True


def test_merge_deliverable_continuation_replaces_intro_only():
    intro = "Aquí le presento una estrategia semanal dirigida a un público"
    body = "1. Público: emprendedores. 2. Lunes: prospección. 3. Martes: contenido."
    merged = merge_deliverable_continuation(intro, body)
    assert merged == body


def test_ensure_complete_voice_reply_retries_incomplete_deliverable():
    async def run():
        llm = GeminiVoiceLlm.__new__(GeminiVoiceLlm)
        llm.user_id = "user-1"
        llm._raw_natural_reply = AsyncMock(
            return_value=(
                "Público objetivo: emprendedores digitales. "
                "Lunes prospección, martes reel, miércoles métricas, "
                "jueves creativos, viernes seguimiento."
            )
        )
        user = "crea una estrategia semanal para CED"
        intro = (
            "Entendido, señor. Aquí le presento una estrategia semanal "
            "enfocada en CED, dirigida a un público"
        )
        with patch("app.services.gemini_voice_llm.build_voice_system", return_value="BASE"):
            result = await llm._ensure_complete_voice_reply(
                intro,
                response=None,
                contents=[],
                user_text=user,
                max_tokens=3200,
                timeout_sec=28.0,
                path="draft_main",
            )
        assert is_deliverable_request(user)
        assert "Lunes" in result or "lunes" in result.lower()
        assert "emprendedores" in result.lower()
        llm._raw_natural_reply.assert_called_once()

    asyncio.run(run())
