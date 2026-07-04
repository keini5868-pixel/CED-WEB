"""Interfaz base — módulos Capa 3."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance


class BaseModule(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}

    @abstractmethod
    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        raise NotImplementedError

    @abstractmethod
    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        raise NotImplementedError

    async def deactivate(self, *, user_id: str, call_id: str) -> None:
        self._state.clear()

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)

    def _idle(self) -> ModuleResult:
        return ModuleResult(conversation_continues=True, handles_response=False)
