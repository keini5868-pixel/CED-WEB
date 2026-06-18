"""Tipos del protocolo Retell Custom LLM WebSocket."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Utterance(BaseModel):
    role: Literal["agent", "user", "system"]
    content: str


class ResponseRequiredRequest(BaseModel):
    interaction_type: Literal["reminder_required", "response_required"]
    response_id: int
    transcript: list[Utterance] = Field(default_factory=list)


class ResponseResponse(BaseModel):
    response_type: Literal["response"] = "response"
    response_id: int
    content: str
    content_complete: bool
    end_call: bool = False
