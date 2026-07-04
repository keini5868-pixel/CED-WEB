"""Módulo publicación FB/IG — Capa 3."""

from __future__ import annotations

import asyncio
import logging
import time

from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_custom_llm import (
    resolve_meta_publish_request,
    resolve_social_comments_request,
)
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)

_publish_guard: dict[str, float] = {}


class PublishModule(BaseModule):
    name = "publish"

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
        comments = resolve_social_comments_request(user_text)
        if comments:
            return await self._read_comments(user_id, comments)
        return await self._run_publish(user_text, utterances or [], user_id)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        comments = resolve_social_comments_request(user_text)
        if comments:
            return await self._read_comments(user_id, comments)
        meta_req = resolve_meta_publish_request(user_text, utterances or [])
        if meta_req:
            return await self._run_publish(user_text, utterances or [], user_id)
        return self._idle()

    async def _read_comments(
        self, user_id: str, comments: dict[str, str]
    ) -> ModuleResult:
        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "leer_comentarios_redes",
                    user_id,
                    {"platform": comments["platform"]},
                ),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="No pude leer los comentarios a tiempo, señor.",
                handles_response=True,
            )
        spoken = str(tool_result.get("spoken") or "").strip() or (
            "No pude consultar los comentarios, señor."
        )
        return ModuleResult(
            ok=True,
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )

    async def _run_publish(
        self,
        user_text: str,
        transcript: list[Utterance],
        user_id: str,
    ) -> ModuleResult:
        meta_req = resolve_meta_publish_request(user_text, transcript)
        if not meta_req:
            return self._idle()

        guard_key = f"{user_id}:{meta_req.get('caption') or user_text}"[:120]
        prev = _publish_guard.get(guard_key, 0.0)
        if time.time() - prev < 30.0:
            dup_spoken = (
                "Publicación enviada con éxito a Instagram, señor."
                if meta_req.get("platform") == "instagram"
                else "Publicación enviada con éxito a Facebook, señor."
            )
            return ModuleResult(ok=True, spoken=dup_spoken, handles_response=True)

        tool_name = (
            "publicar_instagram"
            if meta_req.get("platform") == "instagram"
            else "publicar_facebook"
        )
        tool_args: dict = {"use_last_image": True}
        caption = meta_req.get("caption")
        if caption:
            if tool_name == "publicar_instagram":
                tool_args["caption"] = caption
            else:
                tool_args["mensaje"] = caption

        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(tool_name, user_id, tool_args),
                timeout=35.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="La publicación tardó demasiado, señor. ¿Desea que lo intente de nuevo?",
                handles_response=True,
            )

        _publish_guard[guard_key] = time.time()
        spoken = str(tool_result.get("spoken") or "").strip()
        if not spoken:
            spoken = (
                "No pude publicar, señor. Confirme que adjuntó la imagen."
                if tool_name == "publicar_instagram"
                else "No pude publicar en Facebook, señor."
            )

        return ModuleResult(
            ok=bool(tool_result.get("ok")),
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )
