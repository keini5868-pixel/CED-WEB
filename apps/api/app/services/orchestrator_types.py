"""Tipos compartidos — arquitectura 3 capas CED."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModuleResult:
    ok: bool = True
    spoken: str = ""
    handles_response: bool = False
    conversation_continues: bool = True
    filler: str = ""
    send_filler: bool = False
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    module_activated: str | None = None
    module_result: ModuleResult | None = None
    context_overlay: str | None = None
    conversation_continues: bool = True
    handles_response: bool = False
    spoken: str = ""
    filler: str = ""
    send_filler: bool = False

    @classmethod
    def conversation_only(cls, overlay: str | None = None) -> OrchestratorResult:
        return cls(context_overlay=overlay, conversation_continues=True)
