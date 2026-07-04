"""Módulo memoria / CRM — Capa 3."""

from __future__ import annotations

import asyncio
import re

from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool

_MEMORY_PATTERNS = (
    r"\b(?:recuerda|guarda|anota|memoriza)\b",
    r"\b(?:no\s+olvides|no\s+te\s+olvides)\b",
)


class MemoryModule(BaseModule):
    name = "memory"

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
        self._state = {"last_saved": None}
        return await self._save(user_text, user_id)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        if not _matches_memory(user_text):
            return self._idle()
        return await self._save(user_text, user_id)

    async def _save(self, user_text: str, user_id: str) -> ModuleResult:
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "save_memory",
                    user_id,
                    {"text": user_text, "content": user_text},
                ),
                timeout=12.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="No pude guardar en memoria, señor.",
                handles_response=True,
            )

        spoken = str(tool_result.get("spoken") or "Anotado, señor.").strip()
        return ModuleResult(
            ok=bool(tool_result.get("ok", True)),
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )


def _matches_memory(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in _MEMORY_PATTERNS)
