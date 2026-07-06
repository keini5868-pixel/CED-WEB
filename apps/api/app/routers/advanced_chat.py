"""Chat avanzado — Claude Sonnet + herramientas."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.claude_advanced import (
    ADVANCED_DEEP_MODEL_LABEL,
    ADVANCED_MODEL_LABEL,
    ADVANCED_STREAM_MODEL_LABEL,
    iter_advanced_message_stream,
    send_advanced_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/advanced", tags=["advanced"])


class AdvancedChatTurn(BaseModel):
    role: str
    content: str


class AdvancedChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[AdvancedChatTurn] = Field(default_factory=list)
    conversation_id: str | None = None


@router.post("/chat")
async def advanced_chat(
    body: AdvancedChatRequest,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return send_advanced_message(
            user_id,
            message=body.message,
            history=[t.model_dump() for t in body.history],
            conversation_id=body.conversation_id,
        )
    except ValueError as exc:
        if str(exc) == "missing_anthropic_api_key":
            raise HTTPException(
                status_code=503,
                detail="ANTHROPIC_API_KEY no configurada en Railway.",
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADVANCED] chat failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="No pude obtener respuesta de Claude. Reintenta en un momento.",
        ) from exc


@router.post("/chat/stream")
async def advanced_chat_stream(
    body: AdvancedChatRequest,
    user_id: str = Depends(require_user_id),
) -> StreamingResponse:
    try:
        return StreamingResponse(
            iter_advanced_message_stream(
                user_id,
                message=body.message,
                history=[t.model_dump() for t in body.history],
                conversation_id=body.conversation_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except ValueError as exc:
        if str(exc) == "missing_anthropic_api_key":
            raise HTTPException(
                status_code=503,
                detail="ANTHROPIC_API_KEY no configurada en Railway.",
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADVANCED] stream failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="Error en modo avanzado. Reintenta.",
        ) from exc


@router.get("/status")
def advanced_chat_status(_user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings

    settings = get_settings()
    configured = bool(settings.anthropic_api_key.strip())
    return {
        "configured": configured,
        "model": ADVANCED_DEEP_MODEL_LABEL if configured else None,
        "stream_model": ADVANCED_STREAM_MODEL_LABEL if configured else None,
    }
