"""Gemini standalone — prueba de voz sin orquestador, tools ni filler."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from google.genai import types

from app.services.gemini_voice_llm import (
    _extract_text,
    _gemini_client,
    _response_finish_reason,
    _transcript_to_contents,
    _truncate_contents,
    _voice_model,
)
from app.services.retell_custom_llm import merged_user_query
from app.services.retell_llm_types import ResponseRequiredRequest, ResponseResponse, Utterance
from app.services.voice_llm_common import FALLBACK_REPLY, MAX_HISTORY_TURNS
from app.services.voice_spoken import finalize_voice_delivery_text
from app.services.voice_test_mode import GEMINI_STANDALONE_SYSTEM

logger = logging.getLogger(__name__)

STANDALONE_TIMEOUT_SEC = 18.0
STANDALONE_MAX_TOKENS = 320
STANDALONE_TEMPERATURE = 0.55


class GeminiStandaloneVoiceLlm:
    """Retell → Gemini directo (charla casual). Sin tools ni orquestador."""

    def __init__(self) -> None:
        self.client = _gemini_client()
        self.model = _voice_model()
        self.user_id: str | None = None
        self._history: list[types.Content] = []
        self._latency_call_id = ""
        self._latency_response_id = 0
        self._generate_lock = asyncio.Lock()

    def set_module_overlay(self, overlay: str | None) -> None:
        del overlay

    def set_user_id(self, user_id: str | None) -> None:
        self.user_id = user_id

    def set_latency_context(self, call_id: str, response_id: int) -> None:
        self._latency_call_id = call_id
        self._latency_response_id = response_id

    def take_deferred_batch(self) -> None:
        return None

    async def draft_greeting(self) -> str:
        from app.services.voice_greetings import pick_jarvis_greeting

        greeting = pick_jarvis_greeting(self.user_id)
        if greeting:
            return finalize_voice_delivery_text(greeting)
        return finalize_voice_delivery_text(
            "CED en línea, señor. Estoy listo para conversar."
        )

    async def draft_reminder(self, transcript: list[Utterance]) -> str:
        user_text = merged_user_query(transcript) or "silencio prolongado"
        reply = await self._generate_standalone(
            transcript=transcript,
            user_text=user_text,
            path="standalone_reminder",
        )
        return reply or "¿Sigue ahí, señor?"

    async def draft_conversational_response(
        self,
        request: ResponseRequiredRequest,
    ) -> str | None:
        user_text = merged_user_query(request.transcript)
        if not user_text:
            return None
        return await self._generate_standalone(
            transcript=request.transcript,
            user_text=user_text,
            path="standalone_conversational",
        )

    async def _generate_standalone(
        self,
        *,
        transcript: list[Utterance],
        user_text: str,
        path: str,
    ) -> str | None:
        contents = _transcript_to_contents(transcript)
        if not contents:
            contents = [
                types.Content(role="user", parts=[types.Part(text=user_text)]),
            ]
        elif contents[-1].role != "user":
            contents = [*contents, types.Content(role="user", parts=[types.Part(text=user_text)])]

        history = self._resolve_history(contents)
        last = contents[-1]
        prompt_contents = [*history, last]

        config = types.GenerateContentConfig(
            system_instruction=GEMINI_STANDALONE_SYSTEM,
            temperature=STANDALONE_TEMPERATURE,
            max_output_tokens=STANDALONE_MAX_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )

        started = time.perf_counter()
        try:
            async with self._generate_lock:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.model,
                        contents=prompt_contents,
                        config=config,
                    ),
                    timeout=STANDALONE_TIMEOUT_SEC,
                )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "[VOICE-TEST-GEMINI] timeout path=%s call=%s rid=%s elapsed_ms=%s",
                path,
                self._latency_call_id[:12],
                self._latency_response_id,
                elapsed_ms,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "[VOICE-TEST-GEMINI] error path=%s call=%s rid=%s elapsed_ms=%s err=%s",
                path,
                self._latency_call_id[:12],
                self._latency_response_id,
                elapsed_ms,
                exc,
            )
            return None

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        finish = _response_finish_reason(response)
        raw = " ".join((_extract_text(response) or "").split()).strip()
        text = finalize_voice_delivery_text(raw) if raw else ""

        logger.info(
            "[VOICE-TEST-GEMINI] ok path=%s call=%s rid=%s elapsed_ms=%s "
            "finish=%s chars=%s preview=%s",
            path,
            self._latency_call_id[:12],
            self._latency_response_id,
            elapsed_ms,
            finish,
            len(text),
            text[:120],
        )

        if text:
            self._history = _truncate_contents(
                [
                    *history,
                    last,
                    types.Content(role="model", parts=[types.Part(text=text)]),
                ],
                max_turns=MAX_HISTORY_TURNS,
            )
        return text or None

    def _resolve_history(self, contents: list[types.Content]) -> list[types.Content]:
        if self._history:
            return list(self._history)
        if len(contents) <= 1:
            return []
        return contents[:-1]

    async def draft_response(
        self,
        request: ResponseRequiredRequest,
    ) -> AsyncIterator[ResponseResponse]:
        reply = await self.draft_conversational_response(request)
        yield ResponseResponse(
            response_id=request.response_id,
            content=reply or FALLBACK_REPLY,
            content_complete=True,
            end_call=False,
        )

    async def generate_natural_reply(self, **kwargs: Any) -> str:
        del kwargs
        return ""

    async def generate_empathetic_reformulation(self, **kwargs: Any) -> str | None:
        del kwargs
        return None

    async def apply_deferred_results(self, batch: Any, *, results: list) -> None:
        del batch, results

    def build_async_tool_payload(
        self,
        name: str,
        tool_args: dict,
        tool_result: dict,
    ) -> tuple[str, dict]:
        del name, tool_args, tool_result
        return "Modo prueba standalone — sin herramientas.", {"status": "test_mode"}
