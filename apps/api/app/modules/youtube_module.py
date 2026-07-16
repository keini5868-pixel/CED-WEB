"""Módulo YouTube — Capa 3. Busca y controla reproducción de videos por voz."""

from __future__ import annotations

import asyncio
import logging

from app.modules.base_module import BaseModule
from app.modules.module_acks import MODULE_ACKS
from app.services import voice_client_session as vcs
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance
from app.services.youtube_voice_intent import (
    is_youtube_confirm_no,
    is_youtube_confirm_yes,
    resolve_youtube_control,
    resolve_youtube_play_request,
)
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)

_PLAY_TIMEOUT_SEC = 15.0
_CONTROL_TIMEOUT_SEC = 8.0

_CONTROL_TOOL = {
    "pause": "pause_youtube_video",
    "resume": "resume_youtube_video",
    "close": "close_youtube_player",
}

_CONTROL_FALLBACK_SPOKEN = {
    "pause": "Video en pausa, señor.",
    "resume": "Reanudando el video, señor.",
    "close": "Cerrando YouTube, señor.",
}


class YouTubeModule(BaseModule):
    name = "youtube"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._enter_active()
        vcs.set_active_mode(user_id, "youtube")

        if vcs.is_youtube_awaiting_confirm(user_id):
            if is_youtube_confirm_yes(user_text):
                return await self._play(user_id, "sí")
            if is_youtube_confirm_no(user_text):
                vcs.clear_youtube_pending_confirm(user_id)
                return ModuleResult(
                    ok=True,
                    spoken="De acuerdo, señor. Diga otra canción o video y lo busco.",
                    handles_response=True,
                )

        control = resolve_youtube_control(user_text)
        if control:
            return await self._control(user_id, control)

        play_req = resolve_youtube_play_request(user_text)
        if play_req:
            return await self._play(user_id, str(play_req.get("query") or ""))

        return ModuleResult(
            ok=True,
            spoken="YouTube listo, señor. ¿Qué video desea ver?",
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
        if idle := self._guard_passive():
            return idle

        if vcs.is_youtube_awaiting_confirm(user_id):
            if is_youtube_confirm_yes(user_text):
                return await self._play(user_id, "sí")
            if is_youtube_confirm_no(user_text):
                vcs.clear_youtube_pending_confirm(user_id)
                return ModuleResult(
                    ok=True,
                    spoken="De acuerdo, señor. Diga otra canción o video y lo busco.",
                    handles_response=True,
                )

        control = resolve_youtube_control(user_text)
        if control:
            return await self._control(user_id, control)

        play_req = resolve_youtube_play_request(user_text)
        if play_req:
            return await self._play(user_id, str(play_req.get("query") or ""))

        return self._idle()

    async def deactivate(self, *, user_id: str, call_id: str) -> None:
        await super().deactivate(user_id=user_id, call_id=call_id)
        if vcs.get_active_mode(user_id) == "youtube":
            vcs.set_active_mode(user_id, None)

    async def _play(self, user_id: str, query: str) -> ModuleResult:
        query = (query or "").strip()
        if not query:
            return ModuleResult(
                ok=False,
                spoken="No escuché qué desea ver en YouTube, señor. ¿Puede repetir?",
                handles_response=True,
            )
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "play_youtube_video",
                    user_id,
                    {"query": query},
                ),
                timeout=_PLAY_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="Señor, la búsqueda en YouTube tardó demasiado. ¿Repito?",
                handles_response=True,
                send_filler=True,
                filler=MODULE_ACKS.get("youtube", "Buscando en YouTube, señor."),
            )

        ok = bool(tool_result.get("ok"))
        spoken = str(tool_result.get("spoken") or "").strip()
        if not spoken:
            spoken = (
                f"No encontré un video de {query} en YouTube, señor."
                if not ok
                else "Video listo en pantalla, señor."
            )
        return ModuleResult(
            ok=ok,
            spoken=spoken,
            handles_response=True,
            send_filler=True,
            filler=MODULE_ACKS.get("youtube", "Buscando en YouTube, señor."),
            tool_events=[{"type": "module_activated", "module": self.name}],
        )

    async def _control(self, user_id: str, control: str) -> ModuleResult:
        tool_name = _CONTROL_TOOL[control]
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(tool_name, user_id, {}),
                timeout=_CONTROL_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning("[YOUTUBE_MODULE] control timeout user=%s", user_id[:8])
            tool_result = {"ok": True, "spoken": _CONTROL_FALLBACK_SPOKEN[control]}
        spoken = str(tool_result.get("spoken") or "").strip() or (
            _CONTROL_FALLBACK_SPOKEN[control]
        )
        result = ModuleResult(
            ok=bool(tool_result.get("ok", True)),
            spoken=spoken,
            handles_response=True,
        )
        if control == "close":
            self._active = False
        return result
