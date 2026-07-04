"""Módulo búsqueda web — Capa 3."""

from __future__ import annotations

import asyncio
import logging

from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_custom_llm import (
    format_web_delivery,
    resolve_web_search_request,
    web_search_hold_phrase,
)
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)


class WebSearchModule(BaseModule):
    name = "web_search"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._state["activated"] = True
        return await self._search(user_text, utterances or [], user_id)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        web_req = resolve_web_search_request(user_text, utterances or [])
        if web_req:
            return await self._search(user_text, utterances or [], user_id)
        return self._idle()

    async def _search(
        self,
        user_text: str,
        transcript: list[Utterance],
        user_id: str,
    ) -> ModuleResult:
        web_req = resolve_web_search_request(user_text, transcript)
        if not web_req:
            return self._idle()

        kind = str(web_req.get("kind") or "general")
        query = str(web_req.get("query") or user_text).strip()
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "search_web",
                    user_id,
                    {"query": query, "kind": kind},
                ),
                timeout=17.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="Señor, la búsqueda tardó demasiado. ¿Repito?",
                handles_response=True,
                send_filler=True,
                filler=web_search_hold_phrase(kind),
            )

        spoken = str(tool_result.get("spoken") or "").strip()
        if spoken:
            spoken = format_web_delivery(kind, spoken)
        else:
            spoken = "Señor, no pude completar la búsqueda en este momento."

        return ModuleResult(
            ok=bool(tool_result.get("ok", True)),
            spoken=spoken,
            handles_response=True,
            send_filler=True,
            filler=web_search_hold_phrase(kind),
            tool_events=[{"type": "module_activated", "module": self.name}],
        )
