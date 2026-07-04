"""Módulo PDF — Capa 3."""

from __future__ import annotations

import asyncio

from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool


class PdfModule(BaseModule):
    name = "pdf"

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
        return await self._generate_pdf(user_text, user_id)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        return await self._generate_pdf(user_text, user_id)

    async def _generate_pdf(self, user_text: str, user_id: str) -> ModuleResult:
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "generar_pdf",
                    user_id,
                    {
                        "titulo": "Documento CED",
                        "contenido": user_text,
                        "_user_request": user_text,
                    },
                ),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="El PDF tardó demasiado, señor. ¿Lo intento de nuevo?",
                handles_response=True,
            )

        spoken = str(tool_result.get("spoken") or "PDF listo, señor.").strip()
        return ModuleResult(
            ok=bool(tool_result.get("ok")),
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )
