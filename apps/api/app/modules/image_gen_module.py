"""Módulo generación de imágenes — Capa 3."""

from __future__ import annotations

import asyncio

from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool


class ImageGenModule(BaseModule):
    name = "image_gen"

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
        return await self._generate(user_text, user_id)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        return await self._generate(user_text, user_id)

    async def _generate(self, user_text: str, user_id: str) -> ModuleResult:
        prompt = user_text.strip() or "Imagen profesional para redes sociales"
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "generate_image",
                    user_id,
                    {"prompt": prompt},
                ),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="La generación de imagen tardó demasiado, señor.",
                handles_response=True,
            )

        spoken = str(tool_result.get("spoken") or "Imagen generada, señor.").strip()
        return ModuleResult(
            ok=bool(tool_result.get("ok")),
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )
