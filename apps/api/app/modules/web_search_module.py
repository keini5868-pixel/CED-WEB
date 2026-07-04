"""Módulo búsqueda web — Capa 3 (orden 1)."""

from __future__ import annotations

import asyncio
import logging
import re

from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_custom_llm import (
    format_web_delivery,
    resolve_web_search_request,
    web_search_hold_phrase,
)
from app.services.retell_llm_types import Utterance
from app.services.voice_llm_common import WEB_SEARCH_VOICE_FALLBACK
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT_SEC = 17.0
_QUERY_PREFIX = re.compile(
    r"^(?:"
    r"busca(?:r|me)?(?:\s+en\s+internet)?|"
    r"qu[eé]\s+(?:son\s+)?(?:las\s+)?(?:noticias\s+de|noticias\s+de)|"
    r"dime(?:me)?|"
    r"cu[eé]ntame(?:me)?"
    r")\s+",
    re.I,
)


class WebSearchModule(BaseModule):
    name = "web_search"

    def __init__(self) -> None:
        super().__init__()
        self._state = {
            "last_query": "",
            "last_kind": "general",
            "searching": False,
        }

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._active = True
        query = self._extract_query(user_text, utterances or [])
        return await self.search(query, user_id, utterances or [], user_text=user_text)

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
            query = self._extract_query(user_text, utterances or [])
            return await self.search(query, user_id, utterances or [], user_text=user_text)
        return self._idle()

    async def search(
        self,
        query: str,
        user_id: str,
        transcript: list[Utterance],
        *,
        user_text: str = "",
    ) -> ModuleResult:
        web_req = resolve_web_search_request(user_text or query, transcript)
        kind = str(web_req.get("kind") or "general") if web_req else "general"
        clean_query = (query or str(web_req.get("query") if web_req else "") or user_text).strip()
        if not clean_query:
            return ModuleResult(
                ok=False,
                spoken=WEB_SEARCH_VOICE_FALLBACK,
                handles_response=True,
            )

        self._state.update(
            {"searching": True, "last_query": clean_query, "last_kind": kind}
        )
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "search_web",
                    user_id,
                    {"query": clean_query, "kind": kind},
                ),
                timeout=_SEARCH_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            self._state["searching"] = False
            return ModuleResult(
                ok=False,
                spoken="Señor, la búsqueda tardó demasiado. ¿Repito?",
                handles_response=True,
                send_filler=True,
                filler=web_search_hold_phrase(kind),
            )

        self._state["searching"] = False
        spoken = str(tool_result.get("spoken") or "").strip()
        if spoken:
            spoken = format_web_delivery(kind, spoken)
        else:
            spoken = WEB_SEARCH_VOICE_FALLBACK

        return ModuleResult(
            ok=bool(tool_result.get("ok", True)),
            spoken=spoken,
            handles_response=True,
            send_filler=True,
            filler=web_search_hold_phrase(kind),
            tool_events=[{"type": "module_activated", "module": self.name}],
        )

    def _extract_query(self, user_text: str, transcript: list[Utterance]) -> str:
        web_req = resolve_web_search_request(user_text, transcript)
        if web_req:
            return str(web_req.get("query") or user_text).strip()
        cleaned = _QUERY_PREFIX.sub("", (user_text or "").strip()).strip(" ?.:,-")
        return cleaned or (user_text or "").strip()
