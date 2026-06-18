"""Gemini 2.5 Pro — cerebro de voz CED para Retell Custom LLM."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.domain.openai_voice_prompt import CED_MINIMAL_REALTIME_PROMPT
from app.services.gemini_voice_tools import build_gemini_voice_tools
from app.services.retell_custom_llm import (
    concise_reply_for_small_talk,
    is_generic_agent_line,
    is_small_talk,
)
from app.services.retell_llm_types import ResponseRequiredRequest, ResponseResponse, Utterance
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)

BEGIN_SENTENCE = "A su servicio, señor."


def _gemini_client() -> genai.Client:
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY no configurada")
    return genai.Client(api_key=api_key)


def _voice_model() -> str:
    settings = get_settings()
    return settings.gemini_voice_model.strip() or "gemini-2.5-pro"


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

    def set_user_id(self, user_id: str | None) -> None:
        cleaned = (user_id or "").strip()
        if cleaned:
            self.user_id = cleaned

    async def draft_response(
        self,
        request: ResponseRequiredRequest,
    ) -> AsyncIterator[ResponseResponse]:
        contents = _transcript_to_contents(request.transcript)
        if not contents:
            return

        last = contents[-1]
        if last.role != "user":
            return

        # Evitar reprocesar todo el transcript en cada turno
        self._history = contents[:-1]

        user_text = ""
        if last.parts and last.parts[0].text:
            user_text = last.parts[0].text.strip()
        if not user_text:
            return

        if is_small_talk(user_text):
            reply = concise_reply_for_small_talk(user_text)
            self._history = [*self._history, last, types.Content(role="model", parts=[types.Part(text=reply)])]
            logger.info("[RETELL-GEMINI] small_talk=%s", reply)
            yield ResponseResponse(
                response_id=request.response_id,
                content=reply,
                content_complete=True,
                end_call=False,
            )
            return

        logger.info("[RETELL-GEMINI] user=%s text=%s", (self.user_id or "?")[:8], user_text[:120])

        config = types.GenerateContentConfig(
            system_instruction=CED_MINIMAL_REALTIME_PROMPT,
            tools=[self.tools],
            temperature=0.4,
            max_output_tokens=320,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[*self._history, last],
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[RETELL-GEMINI] generate_content failed")
            yield ResponseResponse(
                response_id=request.response_id,
                content="Disculpe, señor. Tuve un inconveniente técnico.",
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
                    tool_result = await execute_voice_tool(name, self.user_id, args)
                    spoken = str(tool_result.get("spoken") or "Completado, señor.")
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
            if len(tool_spoken_parts) > 1:
                final_text = tool_spoken_parts[-1]

            self._history = follow_up_contents
            logger.info("[RETELL-GEMINI] tool agent=%s", final_text[:160])
            yield ResponseResponse(
                response_id=request.response_id,
                content=final_text[:480],
                content_complete=True,
                end_call=False,
            )
            return

        text_response = _extract_text(response)
        if is_generic_agent_line(text_response) or not text_response:
            text_response = concise_reply_for_small_talk(user_text) if is_small_talk(user_text) else "¿En qué puedo ayudarle, señor?"

        self._history = [*self._history, last, types.Content(role="model", parts=[types.Part(text=text_response)])]
        logger.info("[RETELL-GEMINI] agent=%s", text_response[:160])
        yield ResponseResponse(
            response_id=request.response_id,
            content=text_response,
            content_complete=True,
            end_call=False,
        )
