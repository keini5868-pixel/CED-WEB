"""Llama local — cerebro de voz CED para Retell Custom LLM (sin tools autónomas).

El orquestador determinista activa módulos y ejecuta acciones. Llama solo conversa
y pide confirmación; nunca invoca function-calling por su cuenta.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.services.llama_service import (
    LLAMA_CONVERSATIONAL_SYSTEM,
    call_llama_chat,
    call_llama_local,
)
from app.services.retell_custom_llm import merged_user_query
from app.services.retell_llm_types import ResponseRequiredRequest, ResponseResponse, Utterance
from app.services.voice_llm_common import (
    CONVERSATIONAL_TURN_OVERLAY,
    FALLBACK_REPLY,
    GREETING_OVERLAY,
    MAX_HISTORY_TURNS,
    REMINDER_OVERLAY,
    SESSION_MAX_MINUTES,
    build_voice_system,
)
from app.services.voice_response_guard import guard_voice_response
from app.services.voice_spoken import finalize_voice_delivery_text

logger = logging.getLogger(__name__)

LLAMA_VOICE_TIMEOUT_SEC = 12.0


def _utterances_to_messages(utterances: list[Utterance]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for u in utterances:
        role = "user" if u.role == "user" else "assistant"
        text = (u.content or "").strip()
        if text:
            rows.append({"role": role, "content": text})
    return rows


class LlamaVoiceLlm:
    """Sesión Llama por llamada Retell — historial en memoria, sin tools."""

    def __init__(self) -> None:
        self.user_id: str | None = None
        self._history: list[dict[str, str]] = []
        self._session_started = time.monotonic()
        self._turn_count = 0
        self._module_overlay: str = ""
        self._latency_call_id: str = ""
        self._latency_response_id: int = 0

    def set_module_overlay(self, overlay: str | None) -> None:
        self._module_overlay = (overlay or "").strip()

    def take_deferred_batch(self) -> None:
        # Sin tools diferidas — el orquestador ejecuta todo.
        return None

    def build_async_tool_payload(
        self,
        name: str,
        tool_args: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        spoken = str(tool_result.get("spoken") or "Completado, señor.")
        return spoken, {"status": "success", "spoken": spoken}

    async def apply_deferred_results(
        self,
        batch: Any,
        *,
        results: list[tuple[str, dict[str, Any], str]],
    ) -> None:
        return

    def set_latency_context(self, call_id: str, response_id: int) -> None:
        self._latency_call_id = call_id
        self._latency_response_id = response_id

    def set_user_id(self, user_id: str | None) -> None:
        cleaned = (user_id or "").strip()
        if not cleaned:
            return
        if cleaned == self.user_id:
            return
        self.user_id = cleaned
        self._preload_seed_history(cleaned)

    def _preload_seed_history(self, user_id: str) -> None:
        try:
            from app.services.conversation_memory import load_recent_messages_for_llm

            msgs = load_recent_messages_for_llm(user_id, limit=20)
            seed: list[dict[str, str]] = []
            for row in msgs:
                role = "user" if row["role"] == "user" else "assistant"
                seed.append({"role": role, "content": row["content"]})
            self._history = seed[-MAX_HISTORY_TURNS * 2 :]
            if self._history:
                logger.info(
                    "[RETELL-LLAMA] contexto precargado user=%s msgs=%s",
                    user_id[:8],
                    len(self._history),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RETELL-LLAMA] preload context failed: %s", exc)
            self._history = []

    def _maybe_reset_session(self) -> None:
        elapsed_min = (time.monotonic() - self._session_started) / 60.0
        if elapsed_min >= SESSION_MAX_MINUTES or self._turn_count >= MAX_HISTORY_TURNS:
            self._history = []
            self._session_started = time.monotonic()
            self._turn_count = 0

    def _build_system(self, *, extra_overlay: str = "") -> str:
        base = build_voice_system(self.user_id or "", lightweight=True)
        parts = [LLAMA_CONVERSATIONAL_SYSTEM, base]
        if self._module_overlay.strip():
            parts.append(self._module_overlay.strip())
        if extra_overlay.strip():
            parts.append(extra_overlay.strip())
        return "\n\n".join(p for p in parts if p.strip())

    async def _llama_reply(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        timeout: float = LLAMA_VOICE_TIMEOUT_SEC,
    ) -> str:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    call_llama_chat,
                    system=system,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1024,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("[RETELL-LLAMA] timeout call=%s", self._latency_call_id)
            return FALLBACK_REPLY
        except Exception:  # noqa: BLE001
            logger.exception("[RETELL-LLAMA] generate failed call=%s", self._latency_call_id)
            return FALLBACK_REPLY

    async def draft_greeting(self) -> str:
        from app.services.voice_greetings import pick_jarvis_greeting

        # Mismo patrón que Gemini: saludo instantáneo — Retell cuelga si Ollama tarda.
        greeting = pick_jarvis_greeting(self.user_id)
        if greeting:
            logger.info(
                "[RETELL-LLAMA] greeting pool instant user=%s",
                (self.user_id or "?")[:8],
            )
            safe, _ = guard_voice_response(greeting)
            return finalize_voice_delivery_text(
                safe or "CED en línea, señor. Estoy listo para asistirle."
            )

        system = self._build_system(extra_overlay=GREETING_OVERLAY)
        try:
            reply = await asyncio.wait_for(
                asyncio.to_thread(
                    call_llama_local,
                    "Saluda brevemente al usuario. Una sola frase natural, en español.",
                    system=system,
                    temperature=0.6,
                    max_tokens=120,
                ),
                timeout=8.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[RETELL-LLAMA] greeting timeout call=%s", self._latency_call_id)
            return finalize_voice_delivery_text("CED en línea, señor. Estoy listo para asistirle.")
        except Exception:  # noqa: BLE001
            logger.exception("[RETELL-LLAMA] greeting failed call=%s", self._latency_call_id)
            return finalize_voice_delivery_text("CED en línea, señor. Estoy listo para asistirle.")
        safe, _ = guard_voice_response(reply)
        return finalize_voice_delivery_text(safe or "CED en línea, señor. Estoy listo para asistirle.")

    async def draft_reminder(self, transcript: list[Utterance]) -> str:
        system = self._build_system(extra_overlay=REMINDER_OVERLAY)
        messages = _utterances_to_messages(transcript)
        reply = await self._llama_reply(system=system, messages=messages or [{"role": "user", "content": "¿Sigues ahí?"}])
        safe, _ = guard_voice_response(reply)
        return finalize_voice_delivery_text(safe or FALLBACK_REPLY)

    async def draft_conversational_response(self, request: ResponseRequiredRequest) -> str | None:
        user_text = merged_user_query(request.transcript) or ""
        from app.services.voice_small_talk import try_instant_small_talk_voice_reply

        instant = try_instant_small_talk_voice_reply(user_text)
        if instant:
            logger.info("[RETELL-LLAMA] small-talk instant call=%s", self._latency_call_id)
            safe, blocked = guard_voice_response(instant)
            if blocked or not safe:
                return None
            return finalize_voice_delivery_text(safe)

        if not user_text:
            return None
        system = self._build_system(extra_overlay=CONVERSATIONAL_TURN_OVERLAY)
        messages = _utterances_to_messages(request.transcript)
        reply = await self._llama_reply(system=system, messages=messages)
        safe, blocked = guard_voice_response(reply)
        if blocked or not safe:
            return None
        return finalize_voice_delivery_text(safe)

    async def generate_natural_reply(
        self,
        *,
        transcript: list[Utterance],
        user_text: str,
        overlay: str = "",
        path: str = "",
        max_tokens: int = 640,
    ) -> str:
        system = self._build_system(extra_overlay=overlay)
        messages = _utterances_to_messages(transcript)
        if not messages:
            messages = [{"role": "user", "content": user_text}]
        reply = await self._llama_reply(system=system, messages=messages)
        safe, _ = guard_voice_response(reply)
        return finalize_voice_delivery_text(safe or FALLBACK_REPLY)

    async def generate_empathetic_reformulation(
        self,
        user_text: str,
        *,
        transcript: list[Utterance],
        bad_reply: str,
    ) -> str | None:
        system = self._build_system(
            extra_overlay=(
                "Reformula la respuesta anterior de forma más empática y natural. "
                "No repitas errores técnicos."
            ),
        )
        messages = [
            *_utterances_to_messages(transcript),
            {"role": "assistant", "content": bad_reply},
            {"role": "user", "content": user_text},
        ]
        reply = await self._llama_reply(system=system, messages=messages)
        safe, blocked = guard_voice_response(reply)
        if blocked or not safe:
            return None
        return finalize_voice_delivery_text(safe)

    async def draft_response(
        self,
        request: ResponseRequiredRequest,
    ) -> AsyncIterator[ResponseResponse]:
        self._maybe_reset_session()
        user_text = merged_user_query(request.transcript) or ""
        if not user_text and request.transcript:
            for utterance in reversed(request.transcript):
                if utterance.role == "user" and (utterance.content or "").strip():
                    user_text = utterance.content.strip()
                    break

        if not user_text:
            yield ResponseResponse(
                response_id=request.response_id,
                content=FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )
            return

        system = self._build_system()
        messages = _utterances_to_messages(request.transcript)
        if not messages:
            messages = [{"role": "user", "content": user_text}]

        self._turn_count += 1
        reply = await self._llama_reply(system=system, messages=messages)
        safe, blocked = guard_voice_response(reply)
        if blocked:
            safe = FALLBACK_REPLY
        content = finalize_voice_delivery_text(safe or FALLBACK_REPLY)

        # Actualizar historial local
        self._history = [*messages, {"role": "assistant", "content": content}]
        self._history = self._history[-MAX_HISTORY_TURNS * 2 :]

        logger.info(
            "[RETELL-LLAMA] draft_response rid=%s chars=%s path=llama_no_tools",
            request.response_id,
            len(content),
        )
        yield ResponseResponse(
            response_id=request.response_id,
            content=content,
            content_complete=True,
            end_call=False,
        )
