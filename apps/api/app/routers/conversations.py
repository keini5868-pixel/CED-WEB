"""Historial de conversaciones de voz."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import supabase_db

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class AppendMessageBody(BaseModel):
    conversation_id: str
    role: str = Field(pattern="^(user|model|system)$")
    content: str


@router.get("")
def list_conversations(user_id: str = Depends(require_user_id)) -> dict:
    try:
        items = supabase_db.list_conversations(user_id)
        return {"conversations": items}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("")
def start_conversation(
    title: str = "Conversación CED",
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        conv = supabase_db.create_conversation(user_id, title=title)
        return {"conversation": conv}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{conversation_id}/messages")
def get_messages(
    conversation_id: str,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        messages = supabase_db.get_conversation_messages(conversation_id, user_id)
        return {"messages": messages}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/messages")
def append_message(
    body: AppendMessageBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        supabase_db.append_message(
            body.conversation_id,
            user_id,
            body.role,
            body.content,
        )
        return {"ok": True}
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
