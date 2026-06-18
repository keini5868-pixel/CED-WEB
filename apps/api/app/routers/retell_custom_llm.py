"""Retell Custom LLM WebSocket — Gemini 2.5 Pro como cerebro de voz."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.gemini_voice_llm import GeminiVoiceLlm, draft_begin_message
from app.services.retell_call_registry import release_call_user, resolve_call_user
from app.services.retell_custom_llm import should_respond_to_transcript
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance
from app.services.retell_ws_tracker import (
    active_ws_calls,
    mark_greeting_sent,
    mark_ws_connected,
    mark_ws_disconnected,
    note_ws_interaction,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["retell-custom-llm"])


@router.get("/llm-websocket/active")
async def retell_llm_active_connections() -> dict:
    """Conexiones LLM activas — diagnóstico sin auth."""
    rows = active_ws_calls()
    return {"ok": True, "active_count": len(rows), "connections": rows}


@router.websocket("/llm-websocket/{call_id}")
async def retell_llm_websocket(websocket: WebSocket, call_id: str) -> None:
    """Custom LLM endpoint — Retell envía transcripciones, Gemini responde."""
    await websocket.accept()
    mark_ws_connected(call_id)
    logger.info("[RETELL-GEMINI] WebSocket conectado call_id=%s", call_id)

    llm = GeminiVoiceLlm()
    response_lock = asyncio.Lock()
    active_response_id = 0
    debounce_task: asyncio.Task[None] | None = None
    debounce_wait_s = 0.55

    user_id = resolve_call_user(call_id)
    if user_id:
        llm.set_user_id(user_id)
        logger.info("[RETELL-GEMINI] user_id=%s call=%s (registry)", user_id[:8], call_id)

    await websocket.send_json(
        {
            "response_type": "config",
            "config": {"auto_reconnect": True, "call_details": True},
        }
    )

    greeting_sent = False

    async def send_greeting(response_id: int = 0, *, reason: str) -> None:
        nonlocal greeting_sent
        if greeting_sent:
            return
        greeting_sent = True
        begin = draft_begin_message()
        payload = begin.model_dump()
        payload["response_id"] = response_id
        await websocket.send_json(payload)
        mark_greeting_sent(call_id)
        logger.info("[RETELL-GEMINI] saludo enviado call=%s reason=%s", call_id, reason)

    # Igual que el demo oficial Retell: saludo inmediato tras config
    await send_greeting(0, reason="immediate")

    async def greeting_backup() -> None:
        await asyncio.sleep(2.0)
        await send_greeting(0, reason="backup_2s")

    asyncio.create_task(greeting_backup())

    async def handle_message(request_json: dict) -> None:
        nonlocal active_response_id

        interaction = str(request_json.get("interaction_type") or "")
        note_ws_interaction(call_id, interaction)
        logger.info("[RETELL-GEMINI] interaction=%s call=%s", interaction, call_id)

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

        if interaction == "call_details":
            await send_greeting(0, reason="call_details")
            return

        if interaction == "update_only":
            turntaking = request_json.get("turntaking")
            if turntaking:
                logger.info("[RETELL-GEMINI] turntaking=%s call=%s", turntaking, call_id)
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

        nonlocal debounce_task

        if debounce_task and not debounce_task.done():
            debounce_task.cancel()

        async def run_debounced() -> None:
            nonlocal active_response_id
            try:
                await asyncio.sleep(debounce_wait_s)
            except asyncio.CancelledError:
                return

            async with response_lock:
                if response_id < active_response_id:
                    return
                active_response_id = response_id

                async for event in llm.draft_response(request):
                    if event.response_id < active_response_id:
                        break
                    await websocket.send_json(event.model_dump())
                    logger.info(
                        "[RETELL-GEMINI] respuesta enviada call=%s rid=%s chars=%s",
                        call_id,
                        event.response_id,
                        len(event.content or ""),
                    )

        debounce_task = asyncio.create_task(run_debounced())

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
        mark_ws_disconnected(call_id)
        release_call_user(call_id)
        logger.info("[RETELL-GEMINI] WebSocket cerrado call_id=%s", call_id)
