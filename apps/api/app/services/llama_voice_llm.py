"""Llama local — cerebro de voz CED para Retell Custom LLM (sin tools autónomas).

El orquestador determinista activa módulos y ejecuta acciones. Llama solo conversa
y pide confirmación; nunca invoca function-calling por su cuenta.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

from app.services.llama_service import (
    LLAMA_CONVERSATIONAL_SYSTEM,
    call_llama_local,
    call_llama_voice_chat,
    iter_llama_voice_chat_stream,
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
from app.services.voice_latency import get_turn

logger = logging.getLogger(__name__)

LLAMA_VOICE_TIMEOUT_SEC = 25.0


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

    def _build_system(self, *, extra_overlay: str = "", user_text: str = "") -> str:
        base = build_voice_system(self.user_id or "", user_text, lightweight=True)
        parts = [LLAMA_CONVERSATIONAL_SYSTEM, base]
        if self._module_overlay.strip():
            parts.append(self._module_overlay.strip())
        if extra_overlay.strip():
            parts.append(extra_overlay.strip())
        return "\n\n".join(p for p in parts if p.strip())

    async def _cloud_fallback_reply(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        user_text: str = "",
    ) -> str | None:
        try:
            from app.services.cloud_llm_fallback import chat_cloud_reply

            return await asyncio.wait_for(
                asyncio.to_thread(
                    chat_cloud_reply,
                    system=system,
                    messages=messages,
                    user_text=user_text,
                    max_tokens=1024,
                ),
                timeout=15.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RETELL-LLAMA] cloud fallback failed call=%s: %s", self._latency_call_id, exc)
            return None

    async def _llama_reply(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        timeout: float = LLAMA_VOICE_TIMEOUT_SEC,
        user_text: str = "",
        path: str = "llama_chat",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        http_timeout_sec: float | None = None,
        allow_cloud_fallback: bool = True,
    ) -> str:
        turn = (
            get_turn(self._latency_call_id, self._latency_response_id)
            if self._latency_call_id and self._latency_response_id
            else None
        )
        if turn:
            turn.mark_llm_request(path=path)
        try:
            reply = await asyncio.wait_for(
                asyncio.to_thread(
                    call_llama_voice_chat,
                    system=system,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_sec=http_timeout_sec,
                ),
                timeout=timeout,
            )
            if turn and (reply or "").strip():
                turn.mark_llm_first_token()
            if (reply or "").strip():
                return reply
        except asyncio.TimeoutError:
            logger.warning("[RETELL-LLAMA] timeout call=%s path=%s", self._latency_call_id, path)
        except Exception as exc:  # noqa: BLE001
            from app.services.llama_service import LlamaNotReadyError

            if isinstance(exc, LlamaNotReadyError):
                logger.warning("[RETELL-LLAMA] modelo no listo call=%s", self._latency_call_id)
            else:
                logger.exception(
                    "[RETELL-LLAMA] generate failed call=%s path=%s err=%s: %s",
                    self._latency_call_id,
                    path,
                    type(exc).__name__,
                    exc,
                )

        if not allow_cloud_fallback:
            return FALLBACK_REPLY

        cloud = await self._cloud_fallback_reply(
            system=system,
            messages=messages,
            user_text=user_text,
        )
        if cloud:
            logger.info("[RETELL-LLAMA] cloud fallback ok call=%s", self._latency_call_id)
            return cloud
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
        from app.services.voice_casual import (
            LLAMA_CASUAL_MAX_TOKENS,
            LLAMA_CASUAL_TEMPERATURE,
            LLAMA_CASUAL_TIMEOUT_SEC,
            build_casual_llama_system,
            try_internal_knowledge_voice_reply,
        )
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

        kb_reply, kb_source = try_internal_knowledge_voice_reply(user_text)
        if kb_reply:
            logger.info(
                "[RETELL-LLAMA] casual source=%s call=%s text=%s",
                kb_source,
                self._latency_call_id,
                user_text[:60],
            )
            return kb_reply

        system = build_casual_llama_system(user_text)
        logger.info(
            "[RETELL-LLAMA] casual_system_chars=%s call=%s",
            len(system),
            self._latency_call_id,
        )
        messages = _utterances_to_messages(request.transcript)
        reply = await self._llama_reply(
            system=system,
            messages=messages,
            user_text=user_text,
            path="conversational",
            temperature=LLAMA_CASUAL_TEMPERATURE,
            max_tokens=LLAMA_CASUAL_MAX_TOKENS,
            timeout=LLAMA_CASUAL_TIMEOUT_SEC,
            http_timeout_sec=LLAMA_CASUAL_TIMEOUT_SEC,
            allow_cloud_fallback=False,
        )
        logger.info(
            "[RETELL-LLAMA] casual source=llama call=%s text=%s reply_chars=%s",
            self._latency_call_id,
            user_text[:60],
            len(reply or ""),
        )
        safe, blocked = guard_voice_response(reply)
        if blocked or not safe:
            logger.warning(
                "[RETELL-LLAMA] casual guard blocked=%s call=%s preview=%s",
                blocked,
                self._latency_call_id,
                (reply or "")[:80],
            )
            return None
        final = finalize_voice_delivery_text(safe)
        if not final and safe.strip():
            logger.warning(
                "[RETELL-LLAMA] casual finalize emptied reply call=%s preview=%s",
                self._latency_call_id,
                safe[:80],
            )
            final = safe.strip()
        if not final:
            return None
        return final

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
        reply = await self._llama_reply(system=system, messages=messages, user_text=user_text, path="conversational")
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
        reply = await self._llama_reply(system=system, messages=messages, user_text=user_text, path="conversational")
        safe, blocked = guard_voice_response(reply)
        if blocked or not safe:
            return None
        return finalize_voice_delivery_text(safe)

    async def _iter_llama_voice_deltas(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        path: str = "llama_stream",
    ) -> AsyncIterator[tuple[str, str]]:
        """Streaming Llama → (delta, accumulated) para Retell."""
        from app.services.llama_service import iter_llama_voice_chat_stream

        turn = (
            get_turn(self._latency_call_id, self._latency_response_id)
            if self._latency_call_id and self._latency_response_id
            else None
        )
        if turn:
            turn.mark_llm_request(path=path)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
        first_token_marked = False

        def _producer() -> None:
            acc = ""
            try:
                for piece in iter_llama_voice_chat_stream(
                    system=system,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1024,
                ):
                    acc += piece
                    loop.call_soon_threadsafe(queue.put_nowait, ("delta", piece))
                loop.call_soon_threadsafe(queue.put_nowait, ("end", acc))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("err", str(exc)))

        threading.Thread(target=_producer, daemon=True).start()
        acc = ""
        while True:
            kind, payload = await queue.get()
            if kind == "delta" and payload:
                if turn and not first_token_marked:
                    turn.mark_llm_first_token()
                    first_token_marked = True
                acc += payload
                yield payload, acc
            elif kind == "end":
                yield "", payload or acc
                return
            elif kind == "err":
                raise RuntimeError(payload or "llama stream failed")

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
        accumulated = ""
        try:
            async for delta, acc in self._iter_llama_voice_deltas(
                system=system,
                messages=messages,
            ):
                if delta:
                    accumulated = acc
                    safe, blocked = guard_voice_response(delta)
                    if blocked:
                        continue
                    piece = finalize_voice_delivery_text(safe)
                    if piece:
                        yield ResponseResponse(
                            response_id=request.response_id,
                            content=piece,
                            content_complete=False,
                            end_call=False,
                        )
                elif acc:
                    accumulated = acc
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[RETELL-LLAMA] stream failed rid=%s: %s",
                request.response_id,
                exc,
            )
            accumulated = ""

        if not accumulated.strip():
            accumulated = await self._llama_reply(
                system=system,
                messages=messages,
                user_text=user_text,
            )

        safe, blocked = guard_voice_response(accumulated)
        if blocked:
            safe = FALLBACK_REPLY
        content = finalize_voice_delivery_text(safe or FALLBACK_REPLY)

        self._history = [*messages, {"role": "assistant", "content": content}]
        self._history = self._history[-MAX_HISTORY_TURNS * 2 :]

        logger.info(
            "[RETELL-LLAMA] draft_response rid=%s chars=%s path=llama_stream",
            request.response_id,
            len(content),
        )
        yield ResponseResponse(
            response_id=request.response_id,
            content="",
            content_complete=True,
            end_call=False,
        )
