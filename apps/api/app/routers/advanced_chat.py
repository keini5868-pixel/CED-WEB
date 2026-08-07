"""Chat avanzado — módulo aislado (Claude puro)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.advanced_mode import (
    ADVANCED_DEEP_MODEL_LABEL,
    ADVANCED_STREAM_MODEL_LABEL,
    advanced_is_configured,
    iter_advanced_message_stream,
    send_advanced_message,
    send_advanced_message_with_image,
    send_advanced_message_with_pdf,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/advanced", tags=["advanced"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024


class AdvancedChatTurn(BaseModel):
    role: str
    content: str


class AdvancedChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[AdvancedChatTurn] = Field(default_factory=list)
    conversation_id: str | None = None
    client_request_id: str | None = Field(default=None, max_length=80)


@router.post("/chat")
async def advanced_chat(
    body: AdvancedChatRequest,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return await asyncio.to_thread(
            send_advanced_message,
            user_id,
            message=body.message,
            history=[t.model_dump() for t in body.history],
            conversation_id=body.conversation_id,
        )
    except ValueError as exc:
        code = str(exc)
        if code in ("missing_anthropic_api_key", "missing_llm_api_key"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Modo avanzado requiere ANTHROPIC_API_KEY en el servicio API de Railway."
                ),
            ) from exc
        raise HTTPException(status_code=400, detail=code) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADV-MODE] chat failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="No pude obtener respuesta de Claude. Reintenta en un momento.",
        ) from exc


@router.post("/chat/with-image")
async def advanced_chat_with_image(
    content: str = Form(default=""),
    image_mode: str = Form(default="analyze"),
    conversation_id: str | None = Form(default=None),
    history_json: str = Form(default="[]"),
    image: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Imagen demasiado grande. Máximo 5MB.")
        media_type = (image.content_type or "image/jpeg").split(";")[0].strip()
        text = content.strip() or "¿Qué piensas de esta imagen?"
        try:
            import json

            history_raw = json.loads(history_json or "[]")
            history = history_raw if isinstance(history_raw, list) else []
        except json.JSONDecodeError:
            history = []
        return await asyncio.to_thread(
            send_advanced_message_with_image,
            user_id,
            message=text,
            history=history,
            image_bytes=image_bytes,
            image_media_type=media_type,
            image_mode=(image_mode or "analyze").strip().lower(),
            conversation_id=conversation_id,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        code = str(exc)
        if code == "missing_anthropic_api_key":
            raise HTTPException(
                status_code=503,
                detail="Modo avanzado requiere ANTHROPIC_API_KEY.",
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADV-MODE] with-image failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="Error procesando imagen en modo avanzado.",
        ) from exc


@router.post("/chat/with-pdf")
async def advanced_chat_with_pdf(
    content: str = Form(default=""),
    conversation_id: str | None = Form(default=None),
    history_json: str = Form(default="[]"),
    pdf: UploadFile = File(...),
    user_id: str = Depends(require_user_id),
) -> dict:
    from app.services.pdf_ingest import MAX_PDF_BYTES, PdfIngestError

    try:
        pdf_bytes = await pdf.read()
        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"PDF demasiado grande. Máximo {MAX_PDF_BYTES // (1024 * 1024)} MB.",
            )
        text = content.strip()
        try:
            import json

            history_raw = json.loads(history_json or "[]")
            history = history_raw if isinstance(history_raw, list) else []
        except json.JSONDecodeError:
            history = []
        return await asyncio.to_thread(
            send_advanced_message_with_pdf,
            user_id,
            message=text,
            history=history,
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf.filename or "documento.pdf",
            conversation_id=conversation_id,
        )
    except HTTPException:
        raise
    except PdfIngestError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except ValueError as exc:
        code = str(exc)
        if code == "missing_anthropic_api_key":
            raise HTTPException(
                status_code=503,
                detail="Modo avanzado requiere ANTHROPIC_API_KEY.",
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADV-MODE] with-pdf failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="Error procesando PDF en modo avanzado.",
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
        code = str(exc)
        if code in ("missing_anthropic_api_key", "missing_llm_api_key"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Modo avanzado requiere ANTHROPIC_API_KEY en el servicio API de Railway."
                ),
            ) from exc
        raise HTTPException(status_code=400, detail=code) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADV-MODE] stream failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="Error en modo avanzado. Reintenta.",
        ) from exc


@router.get("/status")
def advanced_chat_status(_user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings

    settings = get_settings()
    anthropic = bool(settings.anthropic_api_key.strip())
    configured = advanced_is_configured()
    return {
        "configured": configured,
        "anthropic_configured": anthropic,
        "google_configured": False,
        "model": ADVANCED_DEEP_MODEL_LABEL if anthropic else None,
        "stream_model": ADVANCED_STREAM_MODEL_LABEL if anthropic else None,
    }
