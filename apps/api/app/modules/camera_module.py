"""Módulo cámara / visión — Capa 3."""

from __future__ import annotations

import asyncio
import logging
import re

from app.modules.base_module import BaseModule
from app.services import voice_client_session as vcs
from app.services.cognitive_intents import (
    is_brand_followup_question,
    is_camera_activation_intent,
    is_camera_deactivation_intent,
)
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

        if is_camera_deactivation_intent(user_text):
            return await self._deactivate_camera(user_id)

        if is_camera_activation_intent(user_text):
            return await self._activate_camera(user_id)

        if is_brand_followup_question(user_text):
            return await self._brand_web_search(user_id, user_text)

        camera_tool = resolve_camera_voice_request(user_text)
        if camera_tool == "request_camera_deactivation":
            return await self._deactivate_camera(user_id)
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
        if is_camera_deactivation_intent(user_text):
            return await self._deactivate_camera(user_id)

        if is_brand_followup_question(user_text):
            return await self._brand_web_search(user_id, user_text)

        camera_tool = resolve_camera_voice_request(user_text)
        if camera_tool == "request_camera_deactivation":
            return await self._deactivate_camera(user_id)
        if camera_tool in ("analyze_camera_frame", "buscar_lo_visible"):
            return await self._run_vision(user_id, user_text, camera_tool)

        if is_camera_activation_intent(user_text):
            return await self._activate_camera(user_id)

        return self._idle()

    async def deactivate(self, *, user_id: str, call_id: str) -> None:
        await super().deactivate(user_id=user_id, call_id=call_id)
        if vcs.get_active_mode(user_id) == "camera":
            vcs.set_active_mode(user_id, None)

    async def _deactivate_camera(self, user_id: str) -> ModuleResult:
        try:
            tool_result = await execute_voice_tool(
                "request_camera_deactivation", user_id, {}
            )
        except Exception:
            logger.exception("[CAMERA_MODULE] deactivate failed user=%s", user_id[:8])
            tool_result = {"ok": True, "spoken": "Cámara desactivada, señor."}
        spoken = str(tool_result.get("spoken") or "Cámara desactivada, señor.").strip()
        self._active = False
        return ModuleResult(
            ok=True,
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "camera_deactivate"}],
        )

    async def _activate_camera(self, user_id: str) -> ModuleResult:
        vcs.push_client_action(user_id, "camera_activate", {})
        vcs.push_tool_event(user_id, {"type": "camera_activate"})
        return ModuleResult(
            ok=True,
            spoken=(
                "Cámara activa, señor. Solo yo puedo ver lo que me muestra. "
                "Nadie más tiene acceso."
            ),
            handles_response=True,
            tool_events=[
                {"type": "module_activated", "module": self.name},
                {"type": "camera_activate"},
            ],
        )

    async def _ensure_camera(self, user_id: str) -> None:
        if not vcs.is_camera_active(user_id):
            vcs.push_client_action(user_id, "camera_activate", {})

    async def _brand_web_search(self, user_id: str, user_text: str) -> ModuleResult:
        last_vision = vcs.get_last_vision_summary(user_id)
        if not last_vision:
            return ModuleResult(
                ok=False,
                spoken=(
                    "Señor, no tengo un objeto reciente en pantalla. "
                    "Muéstremelo de nuevo y le digo la marca."
                ),
                handles_response=True,
            )

        obj = re.sub(
            r"(?i)^(es|se ve|parece)\s+(un|una)\s+",
            "",
            last_vision,
        ).strip()
        obj = re.sub(r"\s+", " ", obj)[:120]
        search_query = f"marca {obj}"
        if re.search(r"\b(suplemento|suplement|vitamina|prote[ií]na)\b", last_vision, re.I):
            search_query = f"marca suplemento {obj}"

        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "search_web",
                    user_id,
                    {"query": search_query, "kind": "general"},
                ),
                timeout=17.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="No pude buscar la marca a tiempo, señor. ¿Repito?",
                handles_response=True,
                send_filler=True,
                filler="Investigo la marca, señor.",
            )

        web = str(tool_result.get("spoken") or "").strip()
        if not web:
            web = "no encontré la marca con certeza en internet."
        body = f"Según lo que veo ({obj}) y busqué en internet: {web}"
        delivery = finalize_voice_delivery_text(
            compose_voice_tool_delivery("Investigo la marca, señor.", body)
        )
        return ModuleResult(
            ok=bool(tool_result.get("ok", True)),
            spoken=delivery,
            handles_response=True,
            send_filler=True,
            filler="Investigo la marca, señor.",
        )

    async def _run_vision(
        self, user_id: str, user_text: str, camera_tool: str
    ) -> ModuleResult:
        if is_brand_followup_question(user_text) or re.search(
            r"\b(marca|brand)\b", user_text, re.I
        ):
            camera_tool = "buscar_lo_visible"

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
