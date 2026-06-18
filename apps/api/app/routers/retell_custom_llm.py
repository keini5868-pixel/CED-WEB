"""Retell Custom LLM WebSocket — Gemini 2.5 Pro como cerebro de voz."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.gemini_voice_llm import GeminiVoiceLlm, draft_begin_message
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance

logger = logging.getLogger(__name__)

router = APIRouter(tags=["retell-custom-llm"])


def _extract_user_id(payload: dict) -> str | None:
    call = payload.get("call") or {}
    metadata = call.get("metadata") or {}
    user_id = metadata.get("user_id") or metadata.get("userId")
    if user_id:
        return str(user_id).strip() or None
    return None


@router.websocket("/llm-websocket/{call_id}")
async def retell_llm_websocket(websocket: WebSocket, call_id: str) -> None:
    """Custom LLM endpoint — Retell envía transcripciones, Gemini responde."""
    await websocket.accept()
    logger.info("[RETELL-GEMINI] WebSocket conectado call_id=%s", call_id)

    llm = GeminiVoiceLlm()
    response_id = 0

    await websocket.send_json(
        {
            "response_type": "config",
            "config": {"auto_reconnect": True, "call_details": True},
            "response_id": 1,
        }
    )

    begin = draft_begin_message()
    await websocket.send_json(begin.model_dump())

    async def handle_message(request_json: dict) -> None:
        nonlocal response_id

        interaction = request_json.get("interaction_type")
        if interaction == "call_details":
            user_id = _extract_user_id(request_json)
            if user_id:
                llm.set_user_id(user_id)
                logger.info("[RETELL-GEMINI] user_id=%s call=%s", user_id[:8], call_id)
            return

        if interaction == "ping_pong":
            await websocket.send_json(
                {
                    "response_type": "ping_pong",
                    "timestamp": request_json.get("timestamp"),
                }
            )
            return

        if interaction == "update_only":
            user_id = _extract_user_id(request_json)
            if user_id:
                llm.set_user_id(user_id)
            return

        if interaction not in ("response_required", "reminder_required"):
            return

        response_id = int(request_json.get("response_id") or response_id)
        transcript_raw = request_json.get("transcript") or []
        transcript = [
            Utterance(role=item.get("role", "user"), content=str(item.get("content") or ""))
            for item in transcript_raw
            if isinstance(item, dict)
        ]

        user_id = _extract_user_id(request_json)
        if user_id:
            llm.set_user_id(user_id)

        request = ResponseRequiredRequest(
            interaction_type=interaction,
            response_id=response_id,
            transcript=transcript,
        )

        async for event in llm.draft_response(request):
            if event.response_id < response_id:
                break
            await websocket.send_json(event.model_dump())

    try:
        async for data in websocket.iter_json():
            asyncio.create_task(handle_message(data))
    except WebSocketDisconnect:
        logger.info("[RETELL-GEMINI] WebSocket desconectado call_id=%s", call_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RETELL-GEMINI] error call_id=%s: %s", call_id, exc)
        try:
            await websocket.close(code=1011, reason="Server error")
        except Exception:  # noqa: BLE001
            pass
    finally:
        logger.info("[RETELL-GEMINI] WebSocket cerrado call_id=%s", call_id)
