"""Módulo PDF — Capa 3."""

from __future__ import annotations

import asyncio

from app.modules.base_module import BaseModule
from app.services.chat_intents import resolve_pdf_request
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool


def _history_from_utterances(utterances: list[Utterance] | None) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for utterance in utterances or []:
        role = "assistant" if utterance.role != "user" else "user"
        content = (utterance.content or "").strip()
        if content:
            history.append({"role": role, "content": content})
    return history


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
        self._active = True
        self._state = {"generating": False, "last_pdf_path": None}
        return await self._generate_pdf(user_text, user_id, utterances=utterances)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        return await self._generate_pdf(user_text, user_id, utterances=utterances)

    async def _generate_pdf(
        self,
        user_text: str,
        user_id: str,
        *,
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        history = _history_from_utterances(utterances)
        title = "Documento CED"
        body = user_text
        req = resolve_pdf_request(user_text, history)
        if req:
            title, body = req

        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "generar_pdf",
                    user_id,
                    {
                        "titulo": title,
                        "title": title,
                        "contenido": body,
                        "content": body,
                        "_user_request": user_text,
                        "_pdf_fallback_texts": [
                            row["content"]
                            for row in history
                            if row.get("role") == "assistant" and row.get("content")
                        ],
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
