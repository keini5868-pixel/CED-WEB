"""Interfaz base — módulos Capa 3 (mini agentes pasivos)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance


class BaseModule(ABC):
    """Mini agente: en reposo no evalúa ni responde; solo actúa cuando está activo."""

    name: str = "base"

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}
        self._active: bool = False
        self._passive: bool = True

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
        self._active = False
        self._passive = True
        await self._on_passive(user_id=user_id, call_id=call_id)

    async def _on_passive(self, *, user_id: str, call_id: str) -> None:
        """Hook al volver a modo recepción pasivo — sin evaluar mensajes."""
        return

    def _enter_active(self) -> None:
        self._active = True
        self._passive = False

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)

    def is_active(self) -> bool:
        return self._active

    def is_passive(self) -> bool:
        return self._passive

    def _idle(self) -> ModuleResult:
        return ModuleResult(conversation_continues=True, handles_response=False)

    def _guard_passive(self) -> ModuleResult | None:
        """Si el agente está pasivo, no procesa el turno."""
        if self._passive or not self._active:
            return self._idle()
        return None
