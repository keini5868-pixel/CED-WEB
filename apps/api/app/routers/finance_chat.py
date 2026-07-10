"""Chat dedicado de Finanzas Personales — registro, análisis y planes."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.finance_chat import (
    FINANCE_MODEL_LABEL,
    FINANCE_STREAM_MODEL_LABEL,
    finance_is_configured,
    iter_finance_message_stream,
    send_finance_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/finance", tags=["finance"])


class FinanceChatTurn(BaseModel):
    role: str
    content: str


class FinanceChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[FinanceChatTurn] = Field(default_factory=list)
    conversation_id: str | None = None


def _handle_llm_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code in ("missing_anthropic_api_key", "missing_llm_api_key"):
        return HTTPException(
            status_code=503,
            detail=(
                "Finanzas no disponible. Configura GOOGLE_API_KEY o "
                "ANTHROPIC_API_KEY en el servicio API de Railway."
            ),
        )
    return HTTPException(status_code=400, detail=code)


@router.post("/chat")
async def finance_chat(
    body: FinanceChatRequest,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return await asyncio.to_thread(
            send_finance_message,
            user_id,
            message=body.message,
            history=[t.model_dump() for t in body.history],
            conversation_id=body.conversation_id,
        )
    except ValueError as exc:
        raise _handle_llm_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[FINANCE] chat failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="No pude procesar sus finanzas. Reintenta en un momento.",
        ) from exc


@router.post("/chat/stream")
async def finance_chat_stream(
    body: FinanceChatRequest,
    user_id: str = Depends(require_user_id),
) -> StreamingResponse:
    try:
        return StreamingResponse(
            iter_finance_message_stream(
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
        raise _handle_llm_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[FINANCE] stream failed user=%s", user_id[:8])
        raise HTTPException(status_code=502, detail="Error en finanzas. Reintenta.") from exc


@router.get("/status")
def finance_chat_status(_user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings
    from app.services.finance_schema import finance_db_diagnostics
    from app.services.llama_service import llama_model, use_llama

    settings = get_settings()
    anthropic = bool(settings.anthropic_api_key.strip())
    google = bool(settings.google_api_key.strip())
    db = finance_db_diagnostics()

    stream_model = (
        llama_model()
        if use_llama()
        else (FINANCE_STREAM_MODEL_LABEL if google else FINANCE_MODEL_LABEL)
    )
    return {
        "configured": finance_is_configured(),
        "anthropic_configured": anthropic,
        "google_configured": google,
        "llama_configured": use_llama(),
        "finance_db_ready": db.get("ready"),
        "finance_db_error": db.get("error"),
        "model": FINANCE_MODEL_LABEL if anthropic else stream_model,
        "stream_model": stream_model,
    }
