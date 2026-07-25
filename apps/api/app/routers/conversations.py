"""Historial de conversaciones de voz."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import supabase_db

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class AppendMessageBody(BaseModel):
    conversation_id: str
    role: str = Field(pattern="^(user|model|system)$")
    content: str
    session_id: str | None = None
    channel: str | None = None


@router.get("")
def list_conversations(
    user_id: str = Depends(require_user_id),
    limit: int = Query(default=50, ge=1, le=100),
    channel: str | None = Query(default=None, pattern="^(voice|text)$"),
    q: str | None = Query(default=None, max_length=120),
) -> dict:
    try:
        items = supabase_db.list_conversations_filtered(
            user_id,
            limit=limit,
            channel=channel,
            q=q,
        )
        return {"conversations": items}
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception(
            "[CONV] list_conversations fallo user=%s", user_id[:8]
        )
        raise HTTPException(
            status_code=503,
            detail="No se pudo cargar el historial.",
        ) from exc


@router.post("")
def start_conversation(
    title: str = "Conversación CED",
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        conv = supabase_db.create_conversation(user_id, title=title)
        return {"conversation": conv}
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc



@router.get("/{conversation_id}/messages")
def get_messages(
    conversation_id: str,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        conv = supabase_db.get_conversation(conversation_id, user_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        messages = supabase_db.get_conversation_messages(conversation_id, user_id)
        return {"messages": messages, "conversation": conv}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/messages")
def append_message(
    body: AppendMessageBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    # Guardar historial es telemetría best-effort: NUNCA debe tumbar el chat ni
    # devolver 500 (que además llega al navegador sin cabeceras CORS y se ve como
    # "el chat no responde"). Si Supabase falla, se registra y se sigue.
    try:
        supabase_db.append_message(
            body.conversation_id,
            user_id,
            body.role,
            body.content,
            session_id=body.session_id,
            channel=body.channel or "voice",
        )
        return {"ok": True, "saved": True}
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — best-effort: no rompas la sesión
        import logging

        logging.getLogger(__name__).warning(
            "[CONV] append_message fallo (best-effort) conv=%s: %s",
            body.conversation_id,
            exc,
        )
        return {"ok": False, "saved": False, "error": "persist_failed"}
