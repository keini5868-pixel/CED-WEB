"""Retell Custom LLM WebSocket — Gemini 2.5 Pro como cerebro de voz."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.gemini_voice_llm import GeminiVoiceLlm, draft_begin_message
from app.services.retell_call_registry import release_call_user, resolve_call_user
from app.services.retell_custom_llm import should_respond_to_transcript
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance

logger = logging.getLogger(__name__)

router = APIRouter(tags=["retell-custom-llm"])


@router.websocket("/llm-websocket/{call_id}")
async def retell_llm_websocket(websocket: WebSocket, call_id: str) -> None:
    """Custom LLM endpoint — Retell envía transcripciones, Gemini responde."""
    await websocket.accept()
    logger.info("[RETELL-GEMINI] WebSocket conectado call_id=%s", call_id)

    llm = GeminiVoiceLlm()
    response_lock = asyncio.Lock()
    active_response_id = 0

    user_id = resolve_call_user(call_id)
    if user_id:
        llm.set_user_id(user_id)
        logger.info("[RETELL-GEMINI] user_id=%s call=%s (registry)", user_id[:8], call_id)

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
        nonlocal active_response_id

        interaction = str(request_json.get("interaction_type") or "")

        uid = resolve_call_user(call_id, request_json)
        if uid:
            llm.set_user_id(uid)

        if interaction == "ping_pong":
            await websocket.send_json(
                {
                    "response_type": "ping_pong",
                    "timestamp": request_json.get("timestamp"),
                }
            )
            return

        if interaction in ("call_details", "update_only"):
            return

        if interaction not in ("response_required", "reminder_required"):
            return

        response_id = int(request_json.get("response_id") or 0)
        transcript_raw = request_json.get("transcript") or []
        transcript = [
            Utterance(role=item.get("role", "user"), content=str(item.get("content") or ""))
            for item in transcript_raw
            if isinstance(item, dict)
        ]

        if not should_respond_to_transcript(transcript, interaction_type=interaction):
            logger.info("[RETELL-GEMINI] skip interaction=%s call=%s", interaction, call_id)
            return

        request = ResponseRequiredRequest(
            interaction_type=interaction,  # type: ignore[arg-type]
            response_id=response_id,
            transcript=transcript,
        )

        async with response_lock:
            if response_id < active_response_id:
                return
            active_response_id = response_id

            async for event in llm.draft_response(request):
                if event.response_id < active_response_id:
                    break
                await websocket.send_json(event.model_dump())

    try:
        async for data in websocket.iter_json():
            await handle_message(data)
    except WebSocketDisconnect:
        logger.info("[RETELL-GEMINI] WebSocket desconectado call_id=%s", call_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RETELL-GEMINI] error call_id=%s: %s", call_id, exc)
        try:
            await websocket.close(code=1011, reason="Server error")
        except Exception:  # noqa: BLE001
            pass
    finally:
        release_call_user(call_id)
        logger.info("[RETELL-GEMINI] WebSocket cerrado call_id=%s", call_id)
