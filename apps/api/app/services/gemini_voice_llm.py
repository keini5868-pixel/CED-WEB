"""Gemini 2.5 Flash — cerebro de voz CED para Retell Custom LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.services.internal_kb_guard import VOICE_KB_LEAK_OVERLAY, contains_internal_kb_leak
from app.services.gemini_voice_tools import build_gemini_voice_tools
from app.services.retell_custom_llm import (
    _needs_internet_lookup,
    format_web_delivery,
    is_generic_agent_line,
    is_unwanted_voice_reply,
    merged_user_query,
    promised_voice_search_without_result,
    resolve_web_search_request,
    web_search_error_phrase,
)
from app.services.retell_llm_types import ResponseRequiredRequest, ResponseResponse, Utterance
from app.services.voice_response_guard import guard_voice_response
from app.services.voice_spoken import (
    chunk_ends_with_punctuation,
    fit_voice_spoken,
    is_advisory_voice_query,
    voice_spoken_limit,
)
from app.services.voice_tool_executor import execute_voice_tool
from app.services.voice_tool_async import (
    DeferredToolBatch,
    DeferredToolCall,
    combined_tool_acknowledgment,
    execute_deferred_tool_batch,
    format_search_web_spoken,
)
from app.services.voice_llm_common import (
    CONVERSATIONAL_TURN_OVERLAY,
    DELAY_ACK_OVERLAY,
    FALLBACK_REPLY,
    GREETING_OVERLAY,
    MAX_HISTORY_TURNS,
    REFORMULATE_EMPATHY_OVERLAY,
    REMINDER_OVERLAY,
    SESSION_MAX_MINUTES,
    WEB_SEARCH_VOICE_FALLBACK,
    build_voice_system,
    log_voice_delivery,
    needs_empathy_reformulation,
    prompt_sha_prefix,
    voice_generation_limits,
)

logger = logging.getLogger(__name__)

PROVIDER = "gemini"
GEMINI_TIMEOUT_SEC = 10.0
GEMINI_ADVISORY_TIMEOUT_SEC = 16.0
GEMINI_CONVERSATIONAL_TIMEOUT_SEC = 12.0
GEMINI_GREETING_TIMEOUT_SEC = 8.0
GEMINI_WEB_TIMEOUT_SEC = 18.0
TOOL_TIMEOUT_SEC = 45.0
SEARCH_WEB_TOOL_TIMEOUT_SEC = 15.0
PDF_TOOL_TIMEOUT_SEC = 90.0

WEB_SEARCH_FALLBACK_OVERLAY = (
    "[Contexto: search_web devolvió status=timeout con fallback=True. "
    "Responde con conocimiento integrado y el disclaimer obligatorio de REGLA 3. "
    "Invoca search_web si aún necesitas datos actuales.]"
)

TRUNCATION_COMPLETE_OVERLAY = (
    "Tu respuesta anterior quedó cortada a mitad de frase. "
    "Completa SOLO lo que falta en 1-2 oraciones naturales. "
    "No repitas el texto ya dicho. Cierra con punto final."
)


def _delivery_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _user_texts_from_gemini_history(history: list[types.Content]) -> list[str]:
    texts: list[str] = []
    for content in history:
        if str(content.role or "") != "user":
            continue
        for part in content.parts or []:
            text = getattr(part, "text", None)
            if text and str(text).strip():
                texts.append(str(text).strip())
    return texts


def _assistant_texts_from_gemini_history(history: list[types.Content]) -> list[str]:
    texts: list[str] = []
    for content in history:
        if str(content.role or "") != "model":
            continue
        for part in content.parts or []:
            text = getattr(part, "text", None)
            if text and str(text).strip():
                texts.append(str(text).strip())
    return texts


def _prompt_sha_prefix() -> str:
    return str(prompt_sha_prefix())


def _voice_generation_limits(user_text: str) -> tuple[int, float]:
    max_tokens, timeout_sec = voice_generation_limits(user_text)
    return max_tokens, timeout_sec


def _log_gemini_delivery(path: str, text: str, *, user_text: str = "") -> None:
    logger.info(
        "[RETELL-GEMINI] response_source=gemini path=%s prompt_sha=%s user=%s chars=%s preview=%s",
        path,
        _prompt_sha_prefix(),
        (user_text or "")[:48],
        len(text),
        text[:120],
    )


def _gemini_client() -> genai.Client:
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY no configurada")
    return genai.Client(api_key=api_key)


def _voice_model() -> str:
    settings = get_settings()
    return settings.gemini_voice_model.strip() or "gemini-2.5-flash"


def _transcript_to_contents(transcript: list[Utterance]) -> list[types.Content]:
    contents: list[types.Content] = []
    for utterance in transcript:
        role = "user" if utterance.role == "user" else "model"
        text = (utterance.content or "").strip()
        if not text:
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    return contents


def _truncate_contents(contents: list[types.Content], *, max_turns: int) -> list[types.Content]:
    if len(contents) <= max_turns:
        return contents
    logger.info("[RETELL-GEMINI] historial truncado %s → %s turnos", len(contents), max_turns)
    return contents[-max_turns:]


def _extract_function_calls(response: types.GenerateContentResponse) -> list[types.FunctionCall]:
    calls: list[types.FunctionCall] = []
    if not response.candidates:
        return calls
    for part in response.candidates[0].content.parts or []:
        if part.function_call:
            calls.append(part.function_call)
    return calls


def _response_finish_reason(response: types.GenerateContentResponse) -> str:
    if not response.candidates:
        return ""
    finish = getattr(response.candidates[0], "finish_reason", None)
    return str(finish or "")


def _response_hit_max_tokens(response: types.GenerateContentResponse) -> bool:
    finish = _response_finish_reason(response).upper()
    return "MAX" in finish and "TOKEN" in finish


def _looks_incomplete_voice_reply(text: str) -> bool:
    cleaned = _delivery_text(text)
    if not cleaned:
        return False
    if cleaned.endswith("..."):
        return True
    return not chunk_ends_with_punctuation(cleaned)


def _extract_text(response: types.GenerateContentResponse) -> str:
    if response.text:
        return response.text.strip()
    chunks: list[str] = []
    if not response.candidates:
        return ""
    for part in response.candidates[0].content.parts or []:
        if part.text:
            chunks.append(part.text.strip())
    return " ".join(chunks).strip()


def _function_call_args(function_call: types.FunctionCall) -> dict[str, Any]:
    raw = function_call.args
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "items"):
        return dict(raw)
    try:
        return json.loads(str(raw))
    except Exception:  # noqa: BLE001
        return {}


def _needs_empathy_reformulation(text: str, *, user_text: str = "") -> bool:
    return needs_empathy_reformulation(text, user_text=user_text)


def _messages_to_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        text = str(msg.get("content") or "").strip()
        if not text:
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    return contents


class GeminiVoiceLlm:
    """Sesión Gemini por llamada Retell — mantiene historial en memoria."""

    def __init__(self) -> None:
        self.client = _gemini_client()
        self.model = _voice_model()
        self.tools = build_gemini_voice_tools()
        self.user_id: str | None = None
        self._history: list[types.Content] = []
        self._seed_history: list[types.Content] = []
        self._session_started = time.monotonic()
        self._turn_count = 0
        self._context_loaded_for: str | None = None
        self._latency_call_id: str = ""
        self._latency_response_id: int = 0
        self._web_search_fallback: bool = False
        self._deferred_batch: DeferredToolBatch | None = None
        self._history_lock = asyncio.Lock()

    def take_deferred_batch(self) -> DeferredToolBatch | None:
        batch = self._deferred_batch
        self._deferred_batch = None
        return batch

    def build_async_tool_payload(
        self,
        name: str,
        tool_args: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if name == "search_web":
            if tool_result.get("fallback") or tool_result.get("status") == "timeout":
                self._web_search_fallback = True
            spoken, payload = format_search_web_spoken(tool_args, tool_result)
            if payload.get("fallback"):
                self._web_search_fallback = True
            return spoken, payload
        if tool_result.get("ok") is False:
            spoken = str(
                tool_result.get("spoken") or "No pude completar la operación, señor."
            )
            return spoken, {
                "status": "error",
                "spoken": spoken,
                "error": tool_result.get("error"),
            }
        spoken = str(tool_result.get("spoken") or "Completado, señor.")
        payload: dict[str, Any] = {"status": "success", "spoken": spoken}
        if name == "generar_pdf" and tool_result.get("file_id"):
            payload["file_id"] = tool_result.get("file_id")
        return spoken, payload

    async def apply_deferred_results(
        self,
        batch: DeferredToolBatch,
        *,
        results: list[tuple[str, dict[str, Any], str]],
    ) -> None:
        if not batch.last_content or not results:
            return
        function_response_parts: list[types.Part] = []
        for name, tool_payload, _spoken in results:
            function_response_parts.append(
                types.Part.from_function_response(name=name, response=tool_payload),
            )
        follow_up_contents = [
            *self._history,
            batch.last_content,
            types.Content(role="model", parts=batch.model_parts),
            types.Content(role="user", parts=function_response_parts),
        ]
        async with self._history_lock:
            self._history = _truncate_contents(follow_up_contents, max_turns=MAX_HISTORY_TURNS)

    def set_latency_context(self, call_id: str, response_id: int) -> None:
        self._latency_call_id = call_id
        self._latency_response_id = response_id

    def set_user_id(self, user_id: str | None) -> None:
        cleaned = (user_id or "").strip()
        if not cleaned:
            return
        if cleaned == self.user_id and self._context_loaded_for == cleaned:
            return
        self.user_id = cleaned
        self._preload_seed_history(cleaned)
        self._context_loaded_for = cleaned

    def _preload_seed_history(self, user_id: str) -> None:
        try:
            from app.services.conversation_memory import load_recent_messages_for_llm

            msgs = load_recent_messages_for_llm(user_id, limit=30)
            seed: list[types.Content] = []
            for row in msgs:
                role = "user" if row["role"] == "user" else "model"
                seed.append(
                    types.Content(role=role, parts=[types.Part(text=row["content"])]),
                )
            self._seed_history = _truncate_contents(seed, max_turns=MAX_HISTORY_TURNS)
            if self._seed_history:
                logger.info(
                    "[RETELL-GEMINI] contexto precargado user=%s msgs=%s",
                    user_id[:8],
                    len(self._seed_history),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RETELL-GEMINI] preload context failed: %s", exc)
            self._seed_history = []

    def _maybe_reset_session(self) -> None:
        elapsed_min = (time.monotonic() - self._session_started) / 60.0
        if elapsed_min >= SESSION_MAX_MINUTES or self._turn_count >= MAX_HISTORY_TURNS:
            logger.info(
                "[RETELL-GEMINI] reinicio sesión user=%s turns=%s min=%.1f",
                (self.user_id or "?")[:8],
                self._turn_count,
                elapsed_min,
            )
            self._history = list(self._seed_history)
            self._session_started = time.monotonic()
            self._turn_count = 0

    def _resolve_history(self, contents: list[types.Content]) -> list[types.Content]:
        if len(contents) > 1:
            return _truncate_contents(contents[:-1], max_turns=MAX_HISTORY_TURNS)
        if self._seed_history:
            return _truncate_contents(list(self._seed_history), max_turns=MAX_HISTORY_TURNS)
        return []

    async def _generate_with_timeout(
        self,
        *,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
        timeout_sec: float | None = None,
        path: str = "generate",
    ) -> types.GenerateContentResponse:
        limit = timeout_sec if timeout_sec is not None else GEMINI_TIMEOUT_SEC

        from app.services.voice_latency import get_turn

        turn = (
            get_turn(self._latency_call_id, self._latency_response_id)
            if self._latency_call_id and self._latency_response_id
            else None
        )
        if turn:
            turn.mark_llm_request(path=path)

        logger.info(
            "[RETELL-GEMINI] model_call start path=%s model=%s prompt_sha=%s user=%s ts=%.3f",
            path,
            self.model,
            _prompt_sha_prefix(),
            (self.user_id or "?")[:8],
            time.time(),
        )
        try:
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                ),
                timeout=limit,
            )
        except Exception:
            logger.warning(
                "[RETELL-GEMINI] model_call failed path=%s prompt_sha=%s user=%s ts=%.3f",
                path,
                _prompt_sha_prefix(),
                (self.user_id or "?")[:8],
                time.time(),
            )
            raise
        logger.info(
            "[RETELL-GEMINI] model_call done path=%s prompt_sha=%s user=%s ts=%.3f",
            path,
            _prompt_sha_prefix(),
            (self.user_id or "?")[:8],
            time.time(),
        )
        return response

    def _build_draft_system(self, user_text: str) -> str:
        system = build_voice_system(self.user_id, user_text)
        if self._web_search_fallback:
            self._web_search_fallback = False
            system = f"{system}\n\n{WEB_SEARCH_FALLBACK_OVERLAY}"
        return system

    async def _ensure_complete_voice_reply(
        self,
        text: str,
        *,
        response: types.GenerateContentResponse | None,
        contents: list[types.Content],
        user_text: str,
        max_tokens: int,
        timeout_sec: float,
        path: str,
    ) -> str:
        cleaned = _delivery_text(text)
        if not cleaned:
            return cleaned
        truncated = (
            response is not None
            and (_response_hit_max_tokens(response) or _looks_incomplete_voice_reply(cleaned))
        )
        if truncated:
            logger.info(
                "[RETELL-GEMINI] truncated reply path=%s finish=%s preview=%s",
                path,
                _response_finish_reason(response) if response else "?",
                cleaned[:80],
            )
            try:
                continuation = await self._raw_natural_reply(
                    contents=[
                        *contents,
                        types.Content(role="model", parts=[types.Part(text=cleaned)]),
                    ],
                    user_text=user_text,
                    overlay=TRUNCATION_COMPLETE_OVERLAY,
                    path=f"{path}_complete",
                    timeout_sec=min(timeout_sec, GEMINI_CONVERSATIONAL_TIMEOUT_SEC),
                    max_tokens=min(320, max_tokens),
                    temperature=0.35,
                )
                if continuation:
                    merged = _delivery_text(f"{cleaned.rstrip('.')} {continuation.lstrip()}".strip())
                    if merged and chunk_ends_with_punctuation(merged):
                        cleaned = merged
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                logger.warning("[RETELL-GEMINI] truncation completion failed path=%s", path)
        if not chunk_ends_with_punctuation(cleaned):
            cleaned = fit_voice_spoken(cleaned, max_chars=voice_spoken_limit(user_text))
        return cleaned

    @staticmethod
    def _search_web_tool_payload(tool_result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if tool_result.get("fallback") or tool_result.get("status") == "timeout":
            spoken = str(
                tool_result.get("spoken") or WEB_SEARCH_VOICE_FALLBACK
            ).strip()
            payload = {
                "status": "timeout",
                "fallback": True,
                "spoken": spoken,
            }
            return spoken, payload
        summary = str(
            tool_result.get("summary") or tool_result.get("spoken") or ""
        ).strip()
        payload: dict[str, Any] = {
            "status": "success",
            "spoken": summary,
            "summary": summary,
        }
        if tool_result.get("source"):
            payload["source"] = tool_result.get("source")
        return summary or "Consulta completada, señor.", payload

    async def _run_voice_search_web(
        self,
        *,
        query: str,
        kind: str,
    ) -> tuple[str, dict[str, Any]]:
        if not self.user_id:
            spoken = "No identifiqué al usuario, señor."
            return spoken, {"status": "error", "spoken": spoken}
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "search_web",
                    self.user_id,
                    {"query": query, "kind": kind},
                ),
                timeout=SEARCH_WEB_TOOL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning("[RETELL-GEMINI] inline search_web timeout query=%s", query[:80])
            tool_result = {
                "status": "timeout",
                "fallback": True,
                "spoken": WEB_SEARCH_VOICE_FALLBACK,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RETELL-GEMINI] inline search_web failed: %s", exc)
            tool_result = {
                "status": "timeout",
                "fallback": True,
                "spoken": WEB_SEARCH_VOICE_FALLBACK,
            }
        spoken, payload = self._search_web_tool_payload(tool_result)
        if payload.get("status") == "success" and spoken:
            return format_web_delivery(kind, spoken), payload
        if spoken:
            return spoken, payload
        return web_search_error_phrase(kind), payload

    async def generate_natural_reply(
        self,
        *,
        contents: list[types.Content] | None = None,
        messages: list[dict[str, Any]] | None = None,
        transcript: list[Utterance] | None = None,
        user_text: str,
        overlay: str,
        path: str,
        timeout_sec: float = GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
        max_tokens: int = 320,
        temperature: float = 0.65,
        with_tools: bool = False,
    ) -> str | None:
        if contents is None:
            if transcript is not None:
                contents = _transcript_to_contents(transcript)
            elif messages is not None:
                contents = _messages_to_contents(messages)
            else:
                return None
        if not contents:
            return None

        text = await self._raw_natural_reply(
            contents=contents,
            user_text=user_text,
            overlay=overlay,
            path=path,
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
            temperature=temperature,
            with_tools=with_tools,
        )
        if not text:
            return None
        safe, blocked = guard_voice_response(text)
        if not blocked and safe:
            log_voice_delivery(PROVIDER, path, safe, user_text=user_text)
            return safe
        if blocked and contains_internal_kb_leak(text):
            logger.warning("[RETELL-GEMINI] KB leak in natural_reply path=%s preview=%s", path, text[:80])
            regen = await self._raw_natural_reply(
                contents=contents,
                user_text=user_text,
                overlay=VOICE_KB_LEAK_OVERLAY,
                path=f"{path}_kb_regen",
                timeout_sec=timeout_sec,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if regen:
                safe2, blocked2 = guard_voice_response(regen)
                if not blocked2 and safe2:
                    log_voice_delivery(PROVIDER, f"{path}_kb_regen", safe2, user_text=user_text)
                    return safe2
        if blocked:
            logger.warning("[RETELL-GEMINI] blocked code leak path=%s preview=%s", path, text[:80])
        return None

    async def _raw_natural_reply(
        self,
        *,
        contents: list[types.Content],
        user_text: str,
        overlay: str,
        path: str,
        timeout_sec: float = GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
        max_tokens: int = 320,
        temperature: float = 0.65,
        with_tools: bool = False,
    ) -> str | None:
        system = f"{build_voice_system(self.user_id, user_text)}\n\n{overlay}"
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[self.tools] if with_tools else None,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        try:
            response = await self._generate_with_timeout(
                contents=contents,
                config=config,
                timeout_sec=timeout_sec,
                path=path,
            )
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            return None
        text = _delivery_text(_extract_text(response))
        if not text:
            return None
        _log_gemini_delivery(path, text, user_text=user_text)
        return text

    async def _sanitize_voice_output(
        self,
        text: str,
        *,
        contents: list[types.Content],
        user_text: str,
        max_tokens: int,
        path: str,
    ) -> str:
        safe, blocked = guard_voice_response(text)
        if not blocked:
            if safe:
                log_voice_delivery(PROVIDER, path, safe, user_text=user_text)
            return safe or text
        if not contains_internal_kb_leak(text):
            logger.warning("[RETELL-GEMINI] blocked code leak path=%s preview=%s", path, text[:80])
            return FALLBACK_REPLY
        logger.warning("[RETELL-GEMINI] KB leak blocked — regenerating path=%s preview=%s", path, text[:80])
        regen = await self._raw_natural_reply(
            contents=contents,
            user_text=user_text,
            overlay=VOICE_KB_LEAK_OVERLAY,
            path=f"{path}_kb_regen",
            max_tokens=max_tokens,
        )
        if regen:
            safe2, blocked2 = guard_voice_response(regen)
            if not blocked2 and safe2:
                log_voice_delivery(PROVIDER, f"{path}_kb_regen", safe2, user_text=user_text)
                return safe2
        return FALLBACK_REPLY

    async def generate_empathetic_reformulation(
        self,
        user_text: str,
        *,
        transcript: list[Utterance] | None = None,
        bad_reply: str = "",
    ) -> str | None:
        contents = _transcript_to_contents(transcript or [])
        if not contents:
            prompt = user_text.strip() or "[mensaje del usuario]"
            contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        else:
            last = contents[-1]
            if last.role != "user":
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=user_text.strip())]),
                )
        history = self._resolve_history(contents)
        last = contents[-1]
        overlay = REFORMULATE_EMPATHY_OVERLAY
        if bad_reply.strip():
            overlay = (
                f"{overlay}\n\nRespuesta deficiente a reemplazar: \"{bad_reply.strip()[:240]}\""
            )
        reply = await self.generate_natural_reply(
            contents=[*history, last],
            user_text=user_text,
            overlay=overlay,
            path="reformulate_empathy",
            timeout_sec=GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
            temperature=0.72,
            max_tokens=320,
        )
        if reply and not _needs_empathy_reformulation(reply, user_text=user_text):
            from app.services.voice_spoken import fit_voice_spoken, voice_spoken_limit
            from app.services.voice_llm_common import ensure_voice_reply

            return ensure_voice_reply(
                fit_voice_spoken(reply, max_chars=voice_spoken_limit(user_text)),
            )
        return None

    async def draft_greeting(self) -> str:
        from app.services.voice_greetings import pick_jarvis_greeting

        greeting = pick_jarvis_greeting(self.user_id)
        if greeting and not _needs_empathy_reformulation(greeting):
            logger.info("[RETELL-GEMINI] greeting pool instant user=%s", (self.user_id or "?")[:8])
            return greeting
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text="[conexión de voz — saludo inicial, el usuario aún no habla]")],
            )
        ]
        text = await self.generate_natural_reply(
            contents=contents,
            user_text="",
            overlay=GREETING_OVERLAY,
            path="greeting",
            timeout_sec=GEMINI_GREETING_TIMEOUT_SEC,
            max_tokens=80,
            temperature=0.7,
        )
        if text and not _needs_empathy_reformulation(text):
            return text
        retry = await self.generate_natural_reply(
            contents=contents,
            user_text="",
            overlay=f"{GREETING_OVERLAY}\n\nReintenta: una sola frase cálida, sin clichés de mayordomo.",
            path="greeting_retry",
            timeout_sec=GEMINI_GREETING_TIMEOUT_SEC,
            max_tokens=80,
            temperature=0.75,
        )
        if retry:
            return retry
        logger.warning("[RETELL-GEMINI] greeting gemini failed — delay_ack fallback")
        delay = await self.generate_natural_reply(
            contents=contents,
            user_text="",
            overlay=DELAY_ACK_OVERLAY,
            path="greeting_delay_ack",
            timeout_sec=GEMINI_GREETING_TIMEOUT_SEC,
            max_tokens=60,
        )
        return delay or FALLBACK_REPLY

    async def draft_reminder(self, transcript: list[Utterance]) -> str:
        contents = _transcript_to_contents(transcript)
        if not contents:
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part(text="[silencio prolongado en la llamada]")],
                )
            ]
        user_text = merged_user_query(transcript) if transcript else ""
        text = await self.generate_natural_reply(
            contents=contents,
            user_text=user_text,
            overlay=REMINDER_OVERLAY,
            path="reminder",
            timeout_sec=GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
            max_tokens=120,
            temperature=0.65,
        )
        if text and not _needs_empathy_reformulation(text, user_text=user_text):
            return text
        retry = await self.generate_empathetic_reformulation(
            user_text or "silencio prolongado",
            transcript=transcript,
            bad_reply=text or "",
        )
        return retry or text or FALLBACK_REPLY

    async def draft_conversational_response(
        self,
        request: ResponseRequiredRequest,
    ) -> str | None:
        """Gemini + prompt CED, sin tools — charla personal y saludos."""
        contents = _transcript_to_contents(request.transcript)
        user_text = merged_user_query(request.transcript)
        if not contents:
            if not user_text:
                return None
            contents = [types.Content(role="user", parts=[types.Part(text=user_text)])]
        elif contents[-1].role != "user":
            if not user_text:
                return None
            contents = [*contents, types.Content(role="user", parts=[types.Part(text=user_text)])]

        last = contents[-1]
        if last.role != "user":
            return None

        if not user_text and last.parts and last.parts[0].text:
            user_text = last.parts[0].text.strip()
        if not user_text:
            return None

        history = self._resolve_history(contents)
        reply = await self.generate_natural_reply(
            contents=[*history, last],
            user_text=user_text,
            overlay=CONVERSATIONAL_TURN_OVERLAY,
            path="conversational",
            timeout_sec=GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
            max_tokens=480,
        )
        if reply and _needs_empathy_reformulation(reply, user_text=user_text):
            reply = await self.generate_empathetic_reformulation(
                user_text,
                transcript=request.transcript,
                bad_reply=reply,
            )
        if not reply:
            reply = await self.generate_natural_reply(
                contents=[*history, last],
                user_text=user_text,
                overlay=DELAY_ACK_OVERLAY,
                path="conversational_delay_ack",
                timeout_sec=GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
                max_tokens=120,
            )
        if not reply:
            reply = await self.generate_empathetic_reformulation(
                user_text,
                transcript=request.transcript,
            )
        if not reply:
            return None

        self._history = _truncate_contents(
            [
                *history,
                last,
                types.Content(role="model", parts=[types.Part(text=reply)]),
            ],
            max_turns=MAX_HISTORY_TURNS,
        )
        self._turn_count += 1
        logger.info("[RETELL-GEMINI] conversational delivered user=%s", user_text[:80])
        from app.services.voice_spoken import finalize_voice_delivery_text

        return finalize_voice_delivery_text(reply)

    async def draft_response(
        self,
        request: ResponseRequiredRequest,
    ) -> AsyncIterator[ResponseResponse]:
        self._maybe_reset_session()
        contents = _transcript_to_contents(request.transcript)
        user_text = merged_user_query(request.transcript) or ""
        if not user_text and request.transcript:
            for utterance in reversed(request.transcript):
                if utterance.role == "user" and (utterance.content or "").strip():
                    user_text = utterance.content.strip()
                    break

        if not contents:
            if not user_text:
                logger.warning(
                    "[RETELL-GEMINI] draft_response vacío rid=%s",
                    request.response_id,
                )
                yield ResponseResponse(
                    response_id=request.response_id,
                    content=FALLBACK_REPLY,
                    content_complete=True,
                    end_call=False,
                )
                return
            contents = [types.Content(role="user", parts=[types.Part(text=user_text)])]
        elif contents[-1].role != "user":
            if not user_text:
                logger.warning(
                    "[RETELL-GEMINI] draft_response sin texto de usuario rid=%s",
                    request.response_id,
                )
                yield ResponseResponse(
                    response_id=request.response_id,
                    content=FALLBACK_REPLY,
                    content_complete=True,
                    end_call=False,
                )
                return
            logger.info(
                "[RETELL-GEMINI] transcript termina en agente — anexando turno usuario rid=%s",
                request.response_id,
            )
            contents = [*contents, types.Content(role="user", parts=[types.Part(text=user_text)])]

        last = contents[-1]
        if last.role != "user":
            logger.warning(
                "[RETELL-GEMINI] draft_response sin turno usuario rid=%s",
                request.response_id,
            )
            yield ResponseResponse(
                response_id=request.response_id,
                content=FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )
            return

        try:
            async for event in self._draft_response_body(request, contents=contents, user_text=user_text, last=last):
                yield event
        except Exception:  # noqa: BLE001
            logger.exception(
                "[RETELL-GEMINI] draft_response unhandled rid=%s user=%s",
                request.response_id,
                user_text[:80],
            )
            yield ResponseResponse(
                response_id=request.response_id,
                content=FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )

    async def _draft_response_body(
        self,
        request: ResponseRequiredRequest,
        *,
        contents: list[types.Content],
        user_text: str,
        last: types.Content,
    ) -> AsyncIterator[ResponseResponse]:
        self._history = self._resolve_history(contents)
        self._turn_count += 1

        if not user_text:
            if last.parts and last.parts[0].text:
                user_text = last.parts[0].text.strip()
        if not user_text:
            yield ResponseResponse(
                response_id=request.response_id,
                content=FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )
            return

        max_tokens, timeout_sec = _voice_generation_limits(user_text)

        from app.services.cognitive_intents import (
            is_internal_knowledge_query,
            is_personal_vent_intent,
            is_web_research_intent,
            requires_live_web,
        )
        from app.services.internal_knowledge import (
            best_internal_answer,
            should_use_internal_brain,
        )

        if is_personal_vent_intent(user_text):
            empathetic = await self.generate_empathetic_reformulation(
                user_text,
                transcript=request.transcript,
                bad_reply="",
            )
            if empathetic:
                from app.services.voice_llm_common import ensure_voice_reply

                spoken = ensure_voice_reply(empathetic)
                self._history = _truncate_contents(
                    [
                        *self._history,
                        last,
                        types.Content(role="model", parts=[types.Part(text=spoken)]),
                    ],
                    max_turns=MAX_HISTORY_TURNS,
                )
                logger.info("[RETELL-GEMINI] personal_vent user=%s", user_text[:80])
                yield ResponseResponse(
                    response_id=request.response_id,
                    content=_delivery_text(spoken),
                    content_complete=True,
                    end_call=False,
                )
                return
            yield ResponseResponse(
                response_id=request.response_id,
                content=FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )
            return

        needs_external_data = (
            requires_live_web(user_text)
            or is_web_research_intent(user_text)
            or _needs_internet_lookup(user_text)
        )
        internal_hit = best_internal_answer(user_text)
        use_internal = (
            not needs_external_data
            and internal_hit
            and should_use_internal_brain(user_text, internal_hit)
            and is_internal_knowledge_query(user_text)
        )
        if use_internal:
            internal_config = types.GenerateContentConfig(
                system_instruction=(
                    f"{build_voice_system(self.user_id, user_text)}\n\n"
                    "Responde SOLO con conocimiento interno CED. "
                    "PROHIBIDO invocar search_web o decir que buscas en internet."
                ),
                temperature=0.4,
                max_output_tokens=max_tokens,
            )
            try:
                internal_response = await self._generate_with_timeout(
                    contents=[*self._history, last],
                    config=internal_config,
                    timeout_sec=timeout_sec,
                    path="internal_brain",
                )
                internal_text = _extract_text(internal_response)
                if internal_text and not is_generic_agent_line(internal_text):
                    internal_text = _delivery_text(internal_text)
                if (
                    internal_text
                    and not is_unwanted_voice_reply(internal_text, user_text=user_text)
                ):
                    _log_gemini_delivery("internal_brain", internal_text, user_text=user_text)
                    self._history = _truncate_contents(
                        [
                            *self._history,
                            last,
                            types.Content(role="model", parts=[types.Part(text=internal_text)]),
                        ],
                        max_turns=MAX_HISTORY_TURNS,
                    )
                    logger.info("[RETELL-GEMINI] internal_brain user=%s", user_text[:80])
                    yield ResponseResponse(
                        response_id=request.response_id,
                        content=internal_text,
                        content_complete=True,
                        end_call=False,
                    )
                    return
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                logger.warning("[RETELL-GEMINI] internal_brain fallback to tools")

        logger.info(
            "[RETELL-GEMINI] user=%s text=%s turns=%s hist=%s",
            (self.user_id or "?")[:8],
            user_text[:120],
            self._turn_count,
            len(self._history),
        )

        system = self._build_draft_system(user_text)
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[self.tools],
            temperature=0.4,
            max_output_tokens=max_tokens,
        )

        try:
            response = await self._generate_with_timeout(
                contents=[*self._history, last],
                config=config,
                timeout_sec=timeout_sec,
                path="draft_main",
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[RETELL-GEMINI] timeout user=%s turns=%s last=%s",
                (self.user_id or "?")[:8],
                self._turn_count,
                user_text[:80],
            )
            delay = await self.generate_natural_reply(
                contents=[*self._history, last],
                user_text=user_text,
                overlay=DELAY_ACK_OVERLAY,
                path="draft_timeout_ack",
                timeout_sec=GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
                max_tokens=120,
            )
            yield ResponseResponse(
                response_id=request.response_id,
                content=delay or FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception(
                "[RETELL-GEMINI] generate_content failed turns=%s hist=%s",
                self._turn_count,
                len(self._history),
            )
            yield ResponseResponse(
                response_id=request.response_id,
                content=FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )
            return

        function_calls = _extract_function_calls(response)
        if function_calls:
            if not response.candidates:
                logger.warning("[RETELL-GEMINI] tool calls without candidates rid=%s", request.response_id)
                yield ResponseResponse(
                    response_id=request.response_id,
                    content=FALLBACK_REPLY,
                    content_complete=True,
                    end_call=False,
                )
                return
            model_parts: list[types.Part] = list(response.candidates[0].content.parts or [])

            deferred_calls: list[DeferredToolCall] = []
            for fc in function_calls:
                name = str(fc.name or "")
                args = _function_call_args(fc)
                logger.info(
                    "[RETELL-GEMINI] tool defer=%s args=%s user=%s",
                    name,
                    args,
                    (self.user_id or "?")[:8],
                )
                tool_args = dict(args)
                if name == "generar_pdf":
                    fallbacks = _assistant_texts_from_gemini_history(self._history)
                    if fallbacks:
                        tool_args["_pdf_fallback_texts"] = fallbacks[-5:]
                    user_texts = _user_texts_from_gemini_history(self._history)
                    tool_args["_user_request"] = (
                        user_text.strip()
                        or (user_texts[-1] if user_texts else "")
                        or str(args.get("titulo") or args.get("title") or "").strip()
                    )
                deferred_calls.append(DeferredToolCall(name=name, args=tool_args))

            self._deferred_batch = DeferredToolBatch(
                calls=deferred_calls,
                user_text=user_text,
                model_parts=model_parts,
                last_content=last,
                on_web_fallback=lambda: setattr(self, "_web_search_fallback", True),
            )
            ack = combined_tool_acknowledgment([c.name for c in deferred_calls])
            logger.info(
                "[RETELL-GEMINI] tool ack immediate user=%s ack=%s",
                (self.user_id or "?")[:8],
                ack[:60],
            )
            yield ResponseResponse(
                response_id=request.response_id,
                content=_delivery_text(ack),
                content_complete=False,
                end_call=False,
            )
            return

        text_response = _delivery_text(_extract_text(response))
        if text_response:
            text_response = await self._ensure_complete_voice_reply(
                text_response,
                response=response,
                contents=[*self._history, last],
                user_text=user_text,
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
                path="draft_main",
            )
            _log_gemini_delivery("draft_main", text_response, user_text=user_text)
        if _needs_empathy_reformulation(text_response, user_text=user_text):
            reformed = await self.generate_empathetic_reformulation(
                user_text,
                transcript=request.transcript,
                bad_reply=text_response,
            )
            if reformed:
                text_response = reformed

        if not text_response:
            conv = await self.draft_conversational_response(request)
            text_response = conv or FALLBACK_REPLY

        web_req = resolve_web_search_request(user_text, request.transcript)
        needs_web = (
            not is_personal_vent_intent(user_text)
            and (_needs_internet_lookup(user_text) or web_req is not None)
        )
        if needs_web and (
            not text_response
            or text_response == FALLBACK_REPLY
            or promised_voice_search_without_result(text_response, user_text=user_text)
            or is_generic_agent_line(text_response)
        ):
            inline_req = web_req or resolve_web_search_request(user_text, request.transcript)
            if inline_req:
                logger.info(
                    "[RETELL-GEMINI] inline search_web safety-net query=%s",
                    str(inline_req.get("query") or "")[:80],
                )
                text_response, _payload = await self._run_voice_search_web(
                    query=str(inline_req.get("query") or user_text),
                    kind=str(inline_req.get("kind") or "general"),
                )
            elif not text_response or text_response == FALLBACK_REPLY:
                text_response = WEB_SEARCH_VOICE_FALLBACK

        text_response = await self._sanitize_voice_output(
            text_response,
            contents=[*self._history, last],
            user_text=user_text,
            max_tokens=max_tokens,
            path="draft_main",
        )

        self._history = _truncate_contents(
            [*self._history, last, types.Content(role="model", parts=[types.Part(text=text_response)])],
            max_turns=MAX_HISTORY_TURNS,
        )
        logger.info("[RETELL-GEMINI] agent=%s", text_response[:160])
        yield ResponseResponse(
            response_id=request.response_id,
            content=_delivery_text(text_response),
            content_complete=True,
            end_call=False,
        )
