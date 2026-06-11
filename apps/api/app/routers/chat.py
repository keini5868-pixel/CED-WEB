"""Chat de texto CED."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import supabase_db
from app.services.text_chat import TextChatError, chat_status, send_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class SendChatBody(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None


@router.get("/status")
def get_chat_status(user_id: str = Depends(require_user_id)) -> dict:
    return chat_status(user_id)


@router.get("/conversations")
def list_text_conversations(
    user_id: str = Depends(require_user_id),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict:
    try:
        items = supabase_db.list_conversations(user_id, channel="text", limit=limit)
        return {"conversations": items}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}/messages")
def get_text_messages(
    conversation_id: str,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        conv = supabase_db.get_conversation(conversation_id, user_id)
        if not conv or conv.get("channel") != "text":
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        messages = supabase_db.get_conversation_messages(conversation_id, user_id)
        return {"messages": messages, "conversation": conv}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/send")
def post_chat_message(
    body: SendChatBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return send_message(
            user_id,
            content=body.content,
            conversation_id=body.conversation_id,
        )
    except TextChatError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] unexpected error")
        raise HTTPException(
            status_code=503,
            detail="Error procesando mensaje. Reintenta.",
        ) from exc
