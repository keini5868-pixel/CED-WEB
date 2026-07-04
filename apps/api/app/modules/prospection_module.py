"""Módulo prospección — Capa 3."""

from __future__ import annotations

import asyncio

from app.modules.base_module import BaseModule
from app.services import voice_client_session as vcs
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool


class ProspectionModule(BaseModule):
    name = "prospection"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        vcs.set_active_mode(user_id, "prospect")
        self._state["activated"] = True
        t = user_text.lower()
        if "desactiv" in t:
            tool = "desactivar_prospeccion"
        elif "reporte" in t:
            tool = "reporte_prospeccion"
        else:
            tool = "activar_prospeccion"

        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(tool, user_id, {}),
                timeout=12.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="La prospección tardó demasiado, señor.",
                handles_response=True,
            )

        spoken = str(tool_result.get("spoken") or "Listo, señor.").strip()
        return ModuleResult(
            ok=bool(tool_result.get("ok")),
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        return await self.activate(
            transcript,
            user_id=user_id,
            call_id=call_id,
            user_text=user_text,
            utterances=utterances,
        )

    async def deactivate(self, *, user_id: str, call_id: str) -> None:
        await super().deactivate(user_id=user_id, call_id=call_id)
        if vcs.get_active_mode(user_id) == "prospect":
            vcs.set_active_mode(user_id, None)
