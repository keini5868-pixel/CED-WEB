"""Chat de texto CED."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import supabase_db
from app.services.chat_multimedia import transcribe_audio
from app.services.text_chat import (
    TextChatError,
    chat_status,
    end_text_conversation,
    iter_send_message_stream,
    send_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024


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


@router.post("/conversations/{conversation_id}/end")
def post_end_text_conversation(
    conversation_id: str,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return end_text_conversation(user_id, conversation_id)
    except TextChatError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] end conversation error")
        raise HTTPException(
            status_code=503,
            detail="No pude cerrar la conversación.",
        ) from exc


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


@router.post("/send/stream")
def post_chat_message_stream(
    body: SendChatBody,
    user_id: str = Depends(require_user_id),
) -> StreamingResponse:
    try:
        return StreamingResponse(
            iter_send_message_stream(
                user_id,
                content=body.content,
                conversation_id=body.conversation_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except TextChatError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] stream error")
        raise HTTPException(
            status_code=503,
            detail="Error procesando mensaje. Reintenta.",
        ) from exc


@router.post("/send-with-image")
async def post_chat_message_with_image(
    content: str = Form(default=""),
    conversation_id: str | None = Form(default=None),
    voice_publish: str = Form(default=""),
    image: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise TextChatError("Imagen demasiado grande. Máximo 5 MB.", http_status=400)
        media_type = (image.content_type or "image/jpeg").split(";")[0].strip()
        text = content.strip() or "¿Qué piensas de esta imagen?"
        want_voice = voice_publish.strip().lower() in ("true", "1", "yes")
        active: str | None = None
        try:
            from app.services import voice_client_session as vcs

            active = vcs.ensure_active_voice_call(user_id)
        except Exception:  # noqa: BLE001
            logger.warning("[CHAT] no se pudo consultar sesión de voz", exc_info=True)
        result = await asyncio.to_thread(
            send_message,
            user_id,
            content=text,
            conversation_id=conversation_id,
            image_bytes=image_bytes,
            image_media_type=media_type,
        )
        if want_voice or active:
            logger.info(
                "[CHAT] imagen registrada para publicar user=%s call=%s",
                user_id[:8],
                (active or "?")[:12],
            )
        return result
    except TextChatError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] send-with-image error")
        raise HTTPException(
            status_code=503,
            detail="Error procesando mensaje con imagen.",
        ) from exc


@router.post("/transcribe")
async def post_transcribe_audio(
    audio: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        audio_bytes = await audio.read()
        filename = audio.filename or "recording.webm"
        text = transcribe_audio(user_id, audio_bytes, filename=filename)
        return {"text": text, "success": True}
    except TextChatError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] transcribe error")
        raise HTTPException(
            status_code=500,
            detail="Error transcribiendo audio.",
        ) from exc
