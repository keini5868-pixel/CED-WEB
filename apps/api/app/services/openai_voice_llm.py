"""OpenAI GPT-4.1 — cerebro conversacional de voz CED para Retell Custom LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.config import get_settings
from app.services.cognitive_intents import is_web_research_intent
from app.services.http_clients import get_openai_async_client
from app.services.openai_key_utils import sanitize_openai_api_key
from app.services.openai_voice_tools import build_openai_chat_tools
from app.services.retell_custom_llm import merged_user_query, _needs_internet_lookup
from app.services.retell_llm_types import ResponseRequiredRequest, ResponseResponse, Utterance
from app.services.voice_llm_common import (
    CONVERSATIONAL_TURN_OVERLAY,
    DELAY_ACK_OVERLAY,
    FALLBACK_REPLY,
    GREETING_OVERLAY,
    MAX_HISTORY_TURNS,
    REFORMULATE_EMPATHY_OVERLAY,
    REMINDER_OVERLAY,
    SESSION_MAX_MINUTES,
    build_voice_system,
    dedupe_voice_reply,
    delivery_text,
    log_voice_delivery,
    needs_empathy_reformulation,
    prompt_sha_prefix,
    transcript_to_openai_messages,
    truncate_messages,
    voice_generation_limits,
    voice_repeats_last_assistant,
)
from app.services.internal_kb_guard import VOICE_KB_LEAK_OVERLAY, contains_internal_kb_leak
from app.services.pdf_report import assistant_fallback_texts_from_messages, user_texts_from_messages
from app.services.voice_spoken import is_prompt_creation_request
from app.services.voice_response_guard import guard_voice_response
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
CONVERSATIONAL_TIMEOUT_SEC = 18.0
GREETING_TIMEOUT_SEC = 12.0
TOOL_TIMEOUT_SEC = 25.0
SEARCH_WEB_TIMEOUT_SEC = 17.0
MAX_TOOL_ROUNDS = 3
PROVIDER = "openai"
# Regresión 6f15302: path ligero desactivado — usar system prompt completo siempre.
VOICE_LIGHTWEIGHT_PATH_ENABLED = False


def _voice_model() -> str:
    settings = get_settings()
    model = getattr(settings, "openai_model_retell_llm", "") or ""
    return model.strip() or "gpt-4.1-mini-2025-04-14"


def _api_key() -> str:
    key = sanitize_openai_api_key(get_settings().openai_api_key)
    if not key:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    return key


def _parse_tool_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


class OpenAIVoiceLlm:
    """Sesión OpenAI GPT-4.1 por llamada Retell — historial + function calling."""

    def __init__(self) -> None:
        self.model = _voice_model()
        self.tools = build_openai_chat_tools()
        self.user_id: str | None = None
        self._history: list[dict[str, Any]] = []
        self._seed_history: list[dict[str, Any]] = []
        self._session_started = time.monotonic()
        self._turn_count = 0
        self._current_user_text = ""
        self._context_loaded_for: str | None = None
        self._pending_advanced: str | None = None
        self._web_search_fallback: bool = False
        self._latency_call_id: str = ""
        self._latency_response_id: int = 0

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

            msgs = load_recent_messages_for_llm(user_id, limit=MAX_HISTORY_TURNS)
            seed: list[dict[str, Any]] = []
            for row in msgs:
                role = "user" if row["role"] == "user" else "assistant"
                seed.append({"role": role, "content": row["content"]})
            self._seed_history = truncate_messages(seed, max_turns=MAX_HISTORY_TURNS)
            if self._seed_history:
                logger.info(
                    "[RETELL-OPENAI] contexto precargado user=%s msgs=%s",
                    user_id[:8],
                    len(self._seed_history),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RETELL-OPENAI] preload context failed: %s", exc)
            self._seed_history = []

    def _maybe_reset_session(self) -> None:
        elapsed_min = (time.monotonic() - self._session_started) / 60.0
        if elapsed_min >= SESSION_MAX_MINUTES or self._turn_count >= MAX_HISTORY_TURNS:
            logger.info(
                "[RETELL-OPENAI] reinicio sesión user=%s turns=%s min=%.1f",
                (self.user_id or "?")[:8],
                self._turn_count,
                elapsed_min,
            )
            self._history = list(self._seed_history)
            self._session_started = time.monotonic()
            self._turn_count = 0

    def _resolve_history(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(messages) > 1:
            return truncate_messages(messages[:-1], max_turns=MAX_HISTORY_TURNS)
        if self._seed_history:
            return truncate_messages(list(self._seed_history), max_turns=MAX_HISTORY_TURNS)
        return []

    async def _chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str,
        path: str,
        timeout_sec: float,
        max_tokens: int = 640,
        temperature: float = 0.4,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        from app.services.voice_latency import get_turn

        turn = (
            get_turn(self._latency_call_id, self._latency_response_id)
            if self._latency_call_id and self._latency_response_id
            else None
        )
        if turn:
            turn.mark_llm_request(path=path)

        logger.info(
            "[RETELL-OPENAI] model_call start path=%s model=%s prompt_sha=%s user=%s ts=%.3f",
            path,
            self.model,
            prompt_sha_prefix(),
            (self.user_id or "?")[:8],
            time.time(),
        )
        headers = {
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        }
        client = get_openai_async_client()
        res = await client.post(
            OPENAI_CHAT_URL,
            headers=headers,
            json=payload,
            timeout=timeout_sec + 2.0,
        )
        if res.status_code >= 400:
            logger.warning(
                "[RETELL-OPENAI] model_call error path=%s status=%s body=%s",
                path,
                res.status_code,
                res.text[:400],
            )
            res.raise_for_status()
        data = res.json()
        if turn:
            turn.mark_llm_first_token()
        logger.info(
            "[RETELL-OPENAI] model_call done path=%s prompt_sha=%s user=%s ts=%.3f",
            path,
            prompt_sha_prefix(),
            (self.user_id or "?")[:8],
            time.time(),
        )
        return data

    def _message_from_response(self, data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices") or []
        if not choices:
            return {}
        return choices[0].get("message") or {}

    async def generate_natural_reply(
        self,
        *,
        messages: list[dict[str, Any]],
        user_text: str,
        overlay: str,
        path: str,
        timeout_sec: float = CONVERSATIONAL_TIMEOUT_SEC,
        max_tokens: int = 320,
        temperature: float = 0.65,
        with_tools: bool = False,
    ) -> str | None:
        text = await self._raw_natural_reply(
            messages=messages,
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
            logger.warning("[RETELL-OPENAI] KB leak in natural_reply path=%s preview=%s", path, text[:80])
            regen = await self._raw_natural_reply(
                messages=messages,
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
            logger.warning("[RETELL-OPENAI] blocked code leak path=%s preview=%s", path, text[:80])
        return None

    async def _sanitize_voice_output(
        self,
        text: str,
        *,
        messages: list[dict[str, Any]],
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
            logger.warning("[RETELL-OPENAI] blocked code leak path=%s preview=%s", path, text[:80])
            return FALLBACK_REPLY
        logger.warning("[RETELL-OPENAI] KB leak blocked — regenerating path=%s preview=%s", path, text[:80])
        regen = await self._raw_natural_reply(
            messages=messages,
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

    async def _raw_natural_reply(
        self,
        *,
        messages: list[dict[str, Any]],
        user_text: str,
        overlay: str,
        path: str,
        timeout_sec: float = CONVERSATIONAL_TIMEOUT_SEC,
        max_tokens: int = 320,
        temperature: float = 0.65,
        with_tools: bool = False,
    ) -> str | None:
        lightweight = (
            VOICE_LIGHTWEIGHT_PATH_ENABLED
            and path
            in {
                "conversational",
                "conversational_delay_ack",
                "greeting",
                "reminder",
                "reformulate_empathy",
            }
        )
        system = (
            f"{build_voice_system(self.user_id, user_text, skip_kb=lightweight, lightweight=lightweight)}"
            f"\n\n{overlay}"
        )
        try:
            data = await self._chat_completion(
                messages=messages,
                system=system,
                path=path,
                timeout_sec=timeout_sec,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=self.tools if with_tools else None,
            )
        except asyncio.TimeoutError:
            logger.warning("[RETELL-OPENAI] natural_reply timeout path=%s", path)
            return None
        except Exception:  # noqa: BLE001
            logger.exception("[RETELL-OPENAI] natural_reply failed path=%s", path)
            return None
        return delivery_text(str(self._message_from_response(data).get("content") or ""))

    async def generate_empathetic_reformulation(
        self,
        user_text: str,
        *,
        transcript: list[Utterance] | None = None,
        bad_reply: str = "",
    ) -> str | None:
        messages = transcript_to_openai_messages(transcript or [])
        if not messages:
            messages = [{"role": "user", "content": user_text.strip() or "[mensaje del usuario]"}]
        elif messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": user_text.strip()})
        history = self._resolve_history(messages)
        last = messages[-1]
        overlay = REFORMULATE_EMPATHY_OVERLAY
        if bad_reply.strip():
            overlay = f'{overlay}\n\nRespuesta deficiente a reemplazar: "{bad_reply.strip()[:240]}"'
        reply = await self.generate_natural_reply(
            messages=[*history, last],
            user_text=user_text,
            overlay=overlay,
            path="reformulate_empathy",
            temperature=0.72,
        )
        if reply and not needs_empathy_reformulation(reply, user_text=user_text):
            return reply
        return None

    async def draft_greeting(self) -> str:
        from app.services.voice_greetings import pick_jarvis_greeting

        greeting = pick_jarvis_greeting(self.user_id)
        logger.info(
            "[RETELL-OPENAI] greeting pool user=%s chars=%s",
            (self.user_id or "?")[:8],
            len(greeting),
        )
        return greeting

    async def draft_reminder(self, transcript: list[Utterance]) -> str:
        messages = transcript_to_openai_messages(transcript)
        if not messages:
            messages = [{"role": "user", "content": "[silencio prolongado en la llamada]"}]
        user_text = merged_user_query(transcript) if transcript else ""
        text = await self.generate_natural_reply(
            messages=messages,
            user_text=user_text,
            overlay=REMINDER_OVERLAY,
            path="reminder",
            max_tokens=120,
            temperature=0.65,
        )
        if text and not needs_empathy_reformulation(text, user_text=user_text):
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
        messages = transcript_to_openai_messages(request.transcript)
        if not messages or messages[-1]["role"] != "user":
            return None
        user_text = merged_user_query(request.transcript)
        if not user_text:
            user_text = str(messages[-1].get("content") or "").strip()
        if not user_text:
            return None
        history = self._resolve_history(messages)
        last = messages[-1]
        reply = await self.generate_natural_reply(
            messages=[*history, last],
            user_text=user_text,
            overlay=CONVERSATIONAL_TURN_OVERLAY,
            path="conversational",
        )
        if reply and needs_empathy_reformulation(reply, user_text=user_text):
            reply = await self.generate_empathetic_reformulation(
                user_text,
                transcript=request.transcript,
                bad_reply=reply,
            )
        if not reply:
            reply = await self.generate_natural_reply(
                messages=[*history, last],
                user_text=user_text,
                overlay=DELAY_ACK_OVERLAY,
                path="conversational_delay_ack",
                max_tokens=120,
            )
        if not reply:
            reply = await self.generate_empathetic_reformulation(
                user_text,
                transcript=request.transcript,
            )
        if not reply:
            return None
        self._history = truncate_messages(
            [*history, last, {"role": "assistant", "content": reply}],
            max_turns=MAX_HISTORY_TURNS,
        )
        self._turn_count += 1
        logger.info("[RETELL-OPENAI] conversational delivered user=%s", user_text[:80])
        return reply

    @staticmethod
    def _search_web_tool_payload(tool_result: dict[str, Any]) -> tuple[str, str]:
        if tool_result.get("fallback") or tool_result.get("status") == "timeout":
            payload = {
                "status": "timeout",
                "fallback": True,
                "spoken": str(tool_result.get("spoken") or "Búsqueda agotada."),
            }
            return payload["spoken"], json.dumps(payload, ensure_ascii=False)
        summary = str(
            tool_result.get("summary") or tool_result.get("spoken") or ""
        ).strip()
        payload = {
            "status": "success",
            "spoken": summary,
            "summary": summary,
        }
        if tool_result.get("source"):
            payload["source"] = tool_result.get("source")
        return summary or "Consulta completada, señor.", json.dumps(payload, ensure_ascii=False)

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        context_messages: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        tool_messages: list[dict[str, Any]] = []
        spoken_parts: list[str] = []
        pdf_fallbacks = assistant_fallback_texts_from_messages(context_messages or [])
        user_texts = user_texts_from_messages(context_messages or [])
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args = _parse_tool_args(fn.get("arguments"))
            if name == "generar_pdf":
                if pdf_fallbacks:
                    args = {**args, "_pdf_fallback_texts": pdf_fallbacks[-3:]}
                if user_texts:
                    args = {**args, "_user_request": user_texts[-1]}
            call_id = str(tc.get("id") or "")
            logger.info(
                "[RETELL-OPENAI] tool=%s args=%s user=%s",
                name,
                args,
                (self.user_id or "?")[:8],
            )
            if not self.user_id:
                spoken = "No identifiqué al usuario, señor."
                content = spoken
            else:
                timeout = SEARCH_WEB_TIMEOUT_SEC if name == "search_web" else TOOL_TIMEOUT_SEC
                try:
                    tool_result = await asyncio.wait_for(
                        execute_voice_tool(name, self.user_id, args),
                        timeout=timeout,
                    )
                    if name == "search_web":
                        spoken, content = self._search_web_tool_payload(tool_result)
                    else:
                        spoken = str(tool_result.get("spoken") or "Completado, señor.")
                        content = spoken
                except asyncio.TimeoutError:
                    logger.warning("[RETELL-OPENAI] tool timeout name=%s", name)
                    if name == "search_web":
                        spoken = "Búsqueda agotada."
                        content = json.dumps(
                            {"status": "timeout", "fallback": True},
                            ensure_ascii=False,
                        )
                    else:
                        spoken = "La operación tardó demasiado, señor. ¿Desea que lo intente de nuevo?"
                        content = spoken
            spoken_parts.append(spoken)
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": content,
                }
            )
        return tool_messages, spoken_parts

    async def draft_response(
        self,
        request: ResponseRequiredRequest,
    ) -> AsyncIterator[ResponseResponse]:
        self._maybe_reset_session()
        user_text = merged_user_query(request.transcript) or ""
        messages = transcript_to_openai_messages(request.transcript)

        if not user_text:
            logger.warning(
                "[RETELL-OPENAI] draft_response sin texto de usuario rid=%s",
                request.response_id,
            )
            yield ResponseResponse(
                response_id=request.response_id,
                content=FALLBACK_REPLY,
                content_complete=True,
                end_call=False,
            )
            return

        if not messages:
            messages = [{"role": "user", "content": user_text}]
        elif messages[-1]["role"] != "user":
            logger.info(
                "[RETELL-OPENAI] transcript termina en agente — anexando turno usuario rid=%s",
                request.response_id,
            )
            messages = [*messages, {"role": "user", "content": user_text}]

        self._history = self._resolve_history(messages)
        self._turn_count += 1
        last = messages[-1]
        if not str(last.get("content") or "").strip():
            last = {"role": "user", "content": user_text}

        self._current_user_text = user_text
        max_tokens, timeout_sec = voice_generation_limits(user_text)

        kb_hits: list = []
        if user_text.strip():
            try:
                from app.services.kb_turn_cache import get_turn_kb_hits

                kb_hits = get_turn_kb_hits(user_text, limit=2)
            except Exception:  # noqa: BLE001
                kb_hits = []

        system = build_voice_system(self.user_id, user_text, kb_hits=kb_hits)

        from app.services.knowledge_router import level_system_overlay, route_knowledge
        from app.services.retell_custom_llm import is_generic_agent_line

        route = route_knowledge(user_text, kb_hits=kb_hits)
        system = f"{system}\n\n{level_system_overlay(route)}"

        kb_injected_in_system = "# CONOCIMIENTO INTERNO CED (prioriza esto" in system

        if getattr(self, "_web_search_fallback", False):
            self._web_search_fallback = False
            system = (
                f"{system}\n\n"
                "[Contexto: search_web devolvió status=timeout con fallback=True. "
                "Responde con conocimiento integrado y el disclaimer obligatorio de REGLA 3.]"
            )

        if route.level == "LEVEL-1" and route.inject and not kb_injected_in_system:
            try:
                data = await self._chat_completion(
                    messages=[*self._history, last],
                    system=system,
                    path="level1_internal",
                    timeout_sec=timeout_sec,
                    max_tokens=max_tokens,
                    temperature=0.4,
                )
                internal_text = delivery_text(
                    str(self._message_from_response(data).get("content") or "")
                )
                internal_text = await self._sanitize_voice_output(
                    internal_text,
                    messages=[*self._history, last],
                    user_text=user_text,
                    max_tokens=max_tokens,
                    path="level1_internal",
                )
                if internal_text and internal_text != FALLBACK_REPLY and not is_generic_agent_line(
                    internal_text
                ):
                    self._history = truncate_messages(
                        [
                            *self._history,
                            last,
                            {"role": "assistant", "content": internal_text},
                        ],
                        max_turns=MAX_HISTORY_TURNS,
                    )
                    yield ResponseResponse(
                        response_id=request.response_id,
                        content=internal_text,
                        content_complete=True,
                        end_call=False,
                    )
                    return
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                logger.warning("[RETELL-OPENAI] level1 fallback to tools")

        logger.info(
            "[RETELL-OPENAI] user=%s text=%s turns=%s hist=%s",
            (self.user_id or "?")[:8],
            user_text[:120],
            self._turn_count,
            len(self._history),
        )

        working_messages = [*self._history, last]
        final_text = FALLBACK_REPLY

        try:
            for round_idx in range(MAX_TOOL_ROUNDS):
                data = await self._chat_completion(
                    messages=working_messages,
                    system=system,
                    path=f"draft_main_r{round_idx}",
                    timeout_sec=timeout_sec,
                    max_tokens=max_tokens,
                    temperature=0.35,
                    tools=self.tools,
                )
                message = self._message_from_response(data)
                tool_calls = message.get("tool_calls") or []

                if tool_calls:
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": message.get("content"),
                        "tool_calls": tool_calls,
                    }
                    tool_messages, spoken_parts = await self._execute_tool_calls(
                        tool_calls,
                        context_messages=working_messages,
                    )
                    working_messages = [*working_messages, assistant_msg, *tool_messages]
                    final_text = spoken_parts[-1] if spoken_parts else "Completado, señor."

                    tool_names = [
                        str((tc.get("function") or {}).get("name") or "") for tc in tool_calls
                    ]
                    only_pdf = all(n == "generar_pdf" for n in tool_names)
                    if only_pdf:
                        logger.info("[RETELL-OPENAI] generar_pdf direct spoken")
                        break

                    follow_data = await self._chat_completion(
                        messages=working_messages,
                        system=system,
                        path="tool_follow_up",
                        timeout_sec=timeout_sec,
                        max_tokens=max_tokens,
                        temperature=0.35,
                    )
                    follow_msg = self._message_from_response(follow_data)
                    follow_text = delivery_text(str(follow_msg.get("content") or ""))
                    safe, blocked = guard_voice_response(follow_text)
                    if not blocked and follow_text:
                        final_text = follow_text
                        log_voice_delivery(PROVIDER, "tool_follow_up", final_text, user_text=user_text)
                    break

                text_response = delivery_text(str(message.get("content") or ""))
                safe, blocked = guard_voice_response(text_response)
                if blocked:
                    logger.warning(
                        "[RETELL-OPENAI] code leak blocked — regenerating user=%s",
                        (self.user_id or "?")[:8],
                    )
                    regen = await self.generate_natural_reply(
                        messages=working_messages,
                        user_text=user_text,
                        overlay=(
                            "Tu respuesta anterior contenía código inválido. "
                            "Responde SOLO en español natural o invoca la herramienta correcta."
                        ),
                        path="code_leak_regen",
                        max_tokens=max_tokens,
                    )
                    final_text = regen or FALLBACK_REPLY
                    break

                if text_response:
                    log_voice_delivery(PROVIDER, "draft_main", text_response, user_text=user_text)
                skip_reformulation = (
                    is_prompt_creation_request(user_text)
                    or len(text_response) > 280
                    or re.search(r"\b1[\.)]\s", text_response)
                )
                if (
                    text_response
                    and needs_empathy_reformulation(text_response, user_text=user_text)
                    and not skip_reformulation
                ):
                    reformed = await self.generate_empathetic_reformulation(
                        user_text,
                        transcript=request.transcript,
                        bad_reply=text_response,
                    )
                    if reformed:
                        text_response = reformed
                if _needs_internet_lookup(user_text) or is_web_research_intent(user_text):
                    final_text = text_response or FALLBACK_REPLY
                else:
                    final_text = (
                        text_response
                        or await self.draft_conversational_response(request)
                        or FALLBACK_REPLY
                    )
                if voice_repeats_last_assistant(final_text, self._history):
                    logger.warning(
                        "[RETELL-OPENAI] duplicate assistant reply — regenerating user=%s",
                        (self.user_id or "?")[:8],
                    )
                    regen = await self.generate_natural_reply(
                        messages=working_messages,
                        user_text=user_text,
                        overlay=(
                            "NO repitas tu mensaje anterior. Responde de forma nueva y útil. "
                            "Si pidió un prompt para una herramienta de IA, entrégalo completo ya."
                        ),
                        path="duplicate_reply_regen",
                        max_tokens=max_tokens,
                    )
                    if regen:
                        final_text = regen
                break
        except asyncio.TimeoutError:
            delay = await self.generate_natural_reply(
                messages=working_messages,
                user_text=user_text,
                overlay=DELAY_ACK_OVERLAY,
                path="draft_timeout_ack",
                max_tokens=120,
            )
            final_text = delay or FALLBACK_REPLY
        except Exception:  # noqa: BLE001
            logger.exception("[RETELL-OPENAI] chat completion failed")
            final_text = FALLBACK_REPLY

        final_text = await self._sanitize_voice_output(
            dedupe_voice_reply(final_text),
            messages=working_messages,
            user_text=user_text,
            max_tokens=max_tokens,
            path="draft_final",
        )

        self._history = truncate_messages(
            [*self._history, last, {"role": "assistant", "content": final_text}],
            max_turns=MAX_HISTORY_TURNS,
        )
        logger.info("[RETELL-OPENAI] agent=%s", final_text[:160])
        yield ResponseResponse(
            response_id=request.response_id,
            content=final_text,
            content_complete=True,
            end_call=False,
        )
