"""Gemini 2.5 Pro — cerebro de voz CED para Retell Custom LLM."""

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
from app.domain.openai_voice_prompt import build_ced_voice_system_prompt
from app.services.gemini_voice_tools import build_gemini_voice_tools
from app.services.retell_custom_llm import (
    empathetic_fallback_reply,
    is_generic_agent_line,
    is_unwanted_voice_reply,
    merged_user_query,
)
from app.services.retell_llm_types import ResponseRequiredRequest, ResponseResponse, Utterance
from app.services.voice_spoken import is_advisory_voice_query
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)

BEGIN_SENTENCE = "A su servicio, señor."
MAX_HISTORY_TURNS = 50
SESSION_MAX_MINUTES = 30.0
GEMINI_TIMEOUT_SEC = 14.0
GEMINI_ADVISORY_TIMEOUT_SEC = 20.0
GEMINI_CONVERSATIONAL_TIMEOUT_SEC = 10.0
FALLBACK_REPLY = "Disculpe, señor. Tuve un inconveniente técnico. ¿Puede repetir?"
TOOL_TIMEOUT_SEC = 25.0

CONVERSATIONAL_TURN_OVERLAY = """
# TURNO CONVERSACIONAL — PRIORIDAD ABSOLUTA
El usuario está en charla personal, saludo casual o comparte algo emocional/cotidiano.
NO invoques herramientas. Responde como Seth: empático, natural, 1-3 oraciones completas.
PROHIBIDO responder solo "¿En qué puedo ayudarle?" o variantes transaccionales.
Valida lo que dice antes de ofrecer ayuda. No fuerces tareas ni prospección.
""".strip()


def _voice_generation_limits(user_text: str) -> tuple[int, float]:
    if is_advisory_voice_query(user_text):
        return 1024, GEMINI_ADVISORY_TIMEOUT_SEC
    return 640, GEMINI_TIMEOUT_SEC


def _delivery_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _gemini_client() -> genai.Client:
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY no configurada")
    return genai.Client(api_key=api_key)


def _voice_model() -> str:
    settings = get_settings()
    return settings.gemini_voice_model.strip() or "gemini-2.5-flash"


def draft_begin_message() -> ResponseResponse:
    return ResponseResponse(
        response_id=0,
        content=BEGIN_SENTENCE,
        content_complete=True,
        end_call=False,
    )


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


def _build_voice_system(user_id: str | None, user_text: str = "") -> str:
    base = build_ced_voice_system_prompt()
    uid = (user_id or "").strip()
    if uid:
        try:
            from app.services.conversation_memory import load_user_context

            ctx = load_user_context(uid)
            if ctx:
                base = f"{base}\n\n{ctx}"
        except Exception:  # noqa: BLE001
            pass
    query = (user_text or "").strip()
    if query and is_advisory_voice_query(query):
        base = (
            f"{base}\n\n"
            "# MODO ASESORÍA (demo / video / estrategia)\n"
            "El usuario pide ideas para demo, video o presentación. "
            "Responde con 3-5 puntos concretos del sistema CED, en español, "
            "oraciones completas, sin cortar a mitad. Cierra con una frase final."
        )
    if query:
        try:
            from app.services.internal_knowledge import format_hits_for_prompt, search_internal_knowledge

            hits = search_internal_knowledge(query, limit=2)
            if hits:
                block = format_hits_for_prompt(hits)
                base = (
                    f"{base}\n\n# CONOCIMIENTO INTERNO CED (prioriza esto; no busques en web salvo noticias/clima/datos de hoy)\n"
                    f"{block}\n\n"
                    "PROHIBIDO decir 'busco en internet', 'consulto la web' o 'un momento mientras busco' "
                    "para este tema. Responde directo como experto interno."
                )
        except Exception:  # noqa: BLE001
            pass
    if uid:
        try:
            from app.services import voice_client_session as vcs

            if vcs.is_camera_active(uid):
                base = (
                    f"{base}\n\n# ESTADO CÁMARA (backend)\n"
                    "Cámara ACTIVA confirmada en el cliente. Puede invocar analyze_camera_frame."
                )
            else:
                base = (
                    f"{base}\n\n# ESTADO CÁMARA (backend)\n"
                    "Cámara APAGADA. No describas nada visual hasta activarla o usar la tool."
                )
        except Exception:  # noqa: BLE001
            pass
    return base


def _extract_function_calls(response: types.GenerateContentResponse) -> list[types.FunctionCall]:
    calls: list[types.FunctionCall] = []
    if not response.candidates:
        return calls
    for part in response.candidates[0].content.parts or []:
        if part.function_call:
            calls.append(part.function_call)
    return calls


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
        self._pending_advanced: str | None = None

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
        logger.info(
            "[RETELL-GEMINI] model_call start path=%s model=%s user=%s ts=%.3f",
            path,
            self.model,
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
                "[RETELL-GEMINI] model_call failed path=%s user=%s ts=%.3f",
                path,
                (self.user_id or "?")[:8],
                time.time(),
            )
            raise
        logger.info(
            "[RETELL-GEMINI] model_call done path=%s user=%s ts=%.3f",
            path,
            (self.user_id or "?")[:8],
            time.time(),
        )
        return response

    async def draft_conversational_response(
        self,
        request: ResponseRequiredRequest,
    ) -> str | None:
        """Gemini + prompt Seth, sin tools — charla personal y saludos."""
        contents = _transcript_to_contents(request.transcript)
        if not contents:
            return None
        last = contents[-1]
        if last.role != "user":
            return None

        user_text = merged_user_query(request.transcript)
        if not user_text and last.parts and last.parts[0].text:
            user_text = last.parts[0].text.strip()
        if not user_text:
            return None

        history = self._resolve_history(contents)
        config = types.GenerateContentConfig(
            system_instruction=(
                f"{_build_voice_system(self.user_id, user_text)}\n\n{CONVERSATIONAL_TURN_OVERLAY}"
            ),
            temperature=0.65,
            max_output_tokens=320,
        )
        try:
            response = await self._generate_with_timeout(
                contents=[*history, last],
                config=config,
                timeout_sec=GEMINI_CONVERSATIONAL_TIMEOUT_SEC,
                path="conversational",
            )
            text = _extract_text(response)
            if not text or is_unwanted_voice_reply(text, user_text=user_text):
                return None
            if is_generic_agent_line(text) and len(text) < 56:
                return None
            delivered = _delivery_text(text)
            self._history = _truncate_contents(
                [
                    *history,
                    last,
                    types.Content(role="model", parts=[types.Part(text=delivered)]),
                ],
                max_turns=MAX_HISTORY_TURNS,
            )
            self._turn_count += 1
            logger.info("[RETELL-GEMINI] conversational user=%s", user_text[:80])
            return delivered
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            logger.warning("[RETELL-GEMINI] conversational turn failed user=%s", user_text[:80])
            return None

    async def draft_response(
        self,
        request: ResponseRequiredRequest,
    ) -> AsyncIterator[ResponseResponse]:
        self._maybe_reset_session()
        contents = _transcript_to_contents(request.transcript)
        if not contents:
            return

        last = contents[-1]
        if last.role != "user":
            return

        self._history = self._resolve_history(contents)
        self._turn_count += 1

        user_text = merged_user_query(request.transcript)
        if not user_text:
            if last.parts and last.parts[0].text:
                user_text = last.parts[0].text.strip()
        if not user_text:
            return

        max_tokens, timeout_sec = _voice_generation_limits(user_text)

        from app.services.cognitive_intents import is_internal_knowledge_query, requires_live_web
        from app.services.internal_knowledge import (
            best_internal_answer,
            should_use_internal_brain,
        )

        internal_hit = best_internal_answer(user_text)
        use_internal = (
            internal_hit
            and should_use_internal_brain(user_text, internal_hit)
            and (is_internal_knowledge_query(user_text) or not requires_live_web(user_text))
        )
        if use_internal:
            internal_config = types.GenerateContentConfig(
                system_instruction=(
                    f"{_build_voice_system(self.user_id, user_text)}\n\n"
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
                        content=_delivery_text(internal_text),
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

        config = types.GenerateContentConfig(
            system_instruction=_build_voice_system(self.user_id, user_text),
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
            yield ResponseResponse(
                response_id=request.response_id,
                content="Un momento, señor. Procesando su solicitud.",
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
            function_response_parts: list[types.Part] = []
            model_parts: list[types.Part] = list(response.candidates[0].content.parts or [])

            tool_spoken_parts: list[str] = []
            for fc in function_calls:
                name = str(fc.name or "")
                args = _function_call_args(fc)
                logger.info("[RETELL-GEMINI] tool=%s args=%s user=%s", name, args, (self.user_id or "?")[:8])

                if not self.user_id:
                    spoken = "No identifiqué al usuario, señor."
                else:
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(name, self.user_id, args),
                            timeout=TOOL_TIMEOUT_SEC,
                        )
                        spoken = str(tool_result.get("spoken") or "Completado, señor.")
                    except asyncio.TimeoutError:
                        logger.warning("[RETELL-GEMINI] tool timeout name=%s", name)
                        spoken = "La operación tardó demasiado, señor. ¿Desea que lo intente de nuevo?"
                tool_spoken_parts.append(spoken)

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": spoken},
                    )
                )

            follow_up_contents = [
                *self._history,
                last,
                types.Content(role="model", parts=model_parts),
                types.Content(role="user", parts=function_response_parts),
            ]

            final_text = tool_spoken_parts[-1] if tool_spoken_parts else "Completado, señor."
            only_claude = function_calls and all(str(fc.name or "") == "consultar_claude" for fc in function_calls)

            if not only_claude:
                try:
                    follow_up = await self._generate_with_timeout(
                        contents=follow_up_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=_build_voice_system(self.user_id, user_text),
                            temperature=0.4,
                            max_output_tokens=max_tokens,
                        ),
                        timeout_sec=timeout_sec,
                        path="tool_follow_up",
                    )
                    follow_text = _extract_text(follow_up)
                    if follow_text:
                        final_text = follow_text
                except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                    logger.warning("[RETELL-GEMINI] tool follow-up failed — using spoken tool result")
            else:
                logger.info("[RETELL-GEMINI] consultar_claude direct spoken (no follow-up)")

            self._history = _truncate_contents(follow_up_contents, max_turns=MAX_HISTORY_TURNS)
            logger.info("[RETELL-GEMINI] tool agent=%s", final_text[:160])
            yield ResponseResponse(
                response_id=request.response_id,
                content=_delivery_text(final_text),
                content_complete=True,
                end_call=False,
            )
            return

        text_response = _extract_text(response)
        if is_unwanted_voice_reply(text_response, user_text=user_text):
            text_response = ""
        if not text_response or (
            is_generic_agent_line(text_response) and len(text_response) < 56
        ):
            text_response = empathetic_fallback_reply(user_text)

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
