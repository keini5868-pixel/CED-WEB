"""Módulo cámara / visión — Capa 3."""

from __future__ import annotations

import asyncio
import logging

from app.modules.base_module import BaseModule
from app.services import voice_client_session as vcs
from app.services.cognitive_intents import is_camera_activation_intent
from app.services.orchestrator_types import ModuleResult
from app.services.retell_custom_llm import resolve_camera_voice_request
from app.services.retell_llm_types import Utterance
from app.services.voice_spoken import (
    compose_voice_tool_delivery,
    finalize_voice_delivery_text,
    format_vision_response,
)
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)


class CameraModule(BaseModule):
    name = "camera"

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
        vcs.set_active_mode(user_id, "camera")

        if is_camera_activation_intent(user_text):
            return await self._activate_camera(user_id)

        camera_tool = resolve_camera_voice_request(user_text)
        if camera_tool in ("analyze_camera_frame", "buscar_lo_visible"):
            await self._ensure_camera(user_id)
            return await self._run_vision(user_id, user_text, camera_tool)

        return await self._activate_camera(user_id)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        camera_tool = resolve_camera_voice_request(user_text)
        if camera_tool in ("analyze_camera_frame", "buscar_lo_visible"):
            return await self._run_vision(user_id, user_text, camera_tool)

        if is_camera_activation_intent(user_text):
            return await self._activate_camera(user_id)

        return self._idle()

    async def deactivate(self, *, user_id: str, call_id: str) -> None:
        await super().deactivate(user_id=user_id, call_id=call_id)
        if vcs.get_active_mode(user_id) == "camera":
            vcs.set_active_mode(user_id, None)

    async def _activate_camera(self, user_id: str) -> ModuleResult:
        if not vcs.is_camera_permission_granted(user_id):
            return ModuleResult(
                ok=False,
                spoken=(
                    "Señor, no tengo permiso de cámara. "
                    "Para activarla, reinicie la sesión y acepte el permiso "
                    "de cámara cuando aparezca."
                ),
                handles_response=True,
            )

        vcs.push_client_action(user_id, "camera_activate", {})
        vcs.push_tool_event(user_id, {"type": "camera_activate"})
        return ModuleResult(
            ok=True,
            spoken="Cámara activa, señor. Lista para analizar.",
            handles_response=True,
            tool_events=[
                {"type": "module_activated", "module": self.name},
                {"type": "camera_activate"},
            ],
        )

    async def _ensure_camera(self, user_id: str) -> None:
        if not vcs.is_camera_active(user_id):
            vcs.push_client_action(user_id, "camera_activate", {})

    async def _run_vision(
        self, user_id: str, user_text: str, camera_tool: str
    ) -> ModuleResult:
        tool_args: dict = {"pregunta": user_text}
        timeout = 40.0
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(camera_tool, user_id, tool_args),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="No pude completar el análisis visual, señor.",
                handles_response=True,
            )

        spoken = str(tool_result.get("spoken") or "").strip()
        body = format_vision_response(spoken) or spoken or (
            "No pude analizar la imagen, señor."
        )
        delivery = finalize_voice_delivery_text(
            compose_voice_tool_delivery(
                "Un momento, señor. Analizo con visión.", body
            )
        )
        return ModuleResult(
            ok=bool(tool_result.get("ok")),
            spoken=delivery,
            handles_response=True,
            send_filler=False,
        )
