"""Retell Custom LLM WebSocket — Gemini 2.5 Pro como cerebro de voz."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.gemini_voice_llm import GeminiVoiceLlm, draft_begin_message
from app.services.retell_call_registry import release_call_user, resolve_call_user
from app.services.retell_custom_llm import (
    concise_reply_for_small_talk,
    is_small_talk,
    last_user_text,
    resolve_web_search_request,
    should_respond_to_transcript,
)
from app.services.voice_tool_executor import execute_voice_tool
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

POST_GREETING_COOLDOWN_S = 1.2


def _normalize_user_key(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


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
    session_started = time.time()
    logger.info("[RETELL-GEMINI] WebSocket conectado call_id=%s", call_id)

    llm = GeminiVoiceLlm()
    response_lock = asyncio.Lock()
    active_response_id = 0
    debounce_task: asyncio.Task[None] | None = None
    debounce_wait_s = 0.45
    post_greeting_ready = asyncio.Event()
    post_greeting_ready.set()
    last_answered_user_key = ""
    generation_cancel = 0
    greeting_release_task: asyncio.Task[None] | None = None
    message_queue: asyncio.Queue[dict | None] = asyncio.Queue()

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

    async def release_post_greeting_cooldown() -> None:
        await asyncio.sleep(POST_GREETING_COOLDOWN_S)
        post_greeting_ready.set()
        logger.info("[RETELL-GEMINI] post-greeting cooldown listo call=%s", call_id)

    async def send_greeting(response_id: int = 0, *, reason: str) -> None:
        nonlocal greeting_sent, greeting_release_task
        if greeting_sent:
            return
        greeting_sent = True
        post_greeting_ready.clear()
        if greeting_release_task and not greeting_release_task.done():
            greeting_release_task.cancel()
        begin = draft_begin_message()
        payload = begin.model_dump()
        payload["response_id"] = response_id
        await websocket.send_json(payload)
        mark_greeting_sent(call_id)
        greeting_release_task = asyncio.create_task(release_post_greeting_cooldown())
        logger.info("[RETELL-GEMINI] saludo enviado call=%s reason=%s", call_id, reason)

    await send_greeting(0, reason="immediate")

    async def handle_message(request_json: dict) -> None:
        nonlocal active_response_id, debounce_task, last_answered_user_key, generation_cancel

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
            if turntaking == "user_turn":
                generation_cancel += 1
                active_response_id += 1
                if debounce_task and not debounce_task.done():
                    debounce_task.cancel()
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

        user_text = last_user_text(transcript)
        user_key = _normalize_user_key(user_text)
        if user_key and user_key == last_answered_user_key:
            logger.info("[RETELL-GEMINI] skip duplicate user turn call=%s", call_id)
            return

        # Nueva pregunta del usuario — invalida respuestas en curso (barge-in).
        active_response_id = max(active_response_id, response_id)

        if debounce_task and not debounce_task.done():
            debounce_task.cancel()

        async def run_debounced() -> None:
            nonlocal active_response_id, last_answered_user_key, generation_cancel
            started_cancel = generation_cancel
            try:
                await post_greeting_ready.wait()
                await asyncio.sleep(debounce_wait_s)
            except asyncio.CancelledError:
                return

            if generation_cancel != started_cancel:
                logger.info("[RETELL-GEMINI] skip cancelled gen call=%s", call_id)
                return

            if response_id < active_response_id:
                logger.info("[RETELL-GEMINI] skip stale rid=%s active=%s", response_id, active_response_id)
                return

            if is_small_talk(user_text) and not resolve_web_search_request(user_text, transcript):
                reply = concise_reply_for_small_talk(user_text)
                async with response_lock:
                    if response_id < active_response_id:
                        return
                    active_response_id = response_id
                    last_answered_user_key = user_key
                    await websocket.send_json(
                        {
                            "response_type": "response",
                            "response_id": response_id,
                            "content": reply,
                            "content_complete": True,
                            "end_call": False,
                        }
                    )
                logger.info("[RETELL-GEMINI] small_talk call=%s: %s", call_id, reply)
                return

            web_req = resolve_web_search_request(user_text, transcript)
            if web_req and uid:
                async with response_lock:
                    if response_id < active_response_id:
                        return
                    active_response_id = response_id
                    last_answered_user_key = user_key
                    tool_result = await execute_voice_tool(
                        "search_web",
                        uid,
                        {"query": web_req["query"], "kind": web_req["kind"]},
                    )
                    if response_id < active_response_id:
                        logger.info("[RETELL-GEMINI] drop stale web rid=%s", response_id)
                        return
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if not spoken or spoken.startswith("No fue posible"):
                        full = spoken or "No pude consultar en internet, señor. Intente de nuevo."
                    else:
                        full = spoken[:480]
                    if response_id < active_response_id:
                        logger.info("[RETELL-GEMINI] drop stale web rid=%s", response_id)
                        return
                    await websocket.send_json(
                        {
                            "response_type": "response",
                            "response_id": response_id,
                            "content": full,
                            "content_complete": True,
                            "end_call": False,
                        }
                    )
                logger.info(
                    "[RETELL-GEMINI] web_search call=%s kind=%s query=%s spoken=%s",
                    call_id,
                    web_req["kind"],
                    web_req["query"][:80],
                    full[:120],
                )
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
                last_answered_user_key = user_key

                try:
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
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "[RETELL-GEMINI] draft_response error call=%s last=%s",
                        call_id,
                        user_text[:80],
                    )
                    await websocket.send_json(
                        {
                            "response_type": "response",
                            "response_id": response_id,
                            "content": "Disculpe, señor. Tuve un inconveniente. ¿Puede repetir?",
                            "content_complete": True,
                            "end_call": False,
                        }
                    )

        debounce_task = asyncio.create_task(run_debounced())

    async def message_worker() -> None:
        while True:
            data = await message_queue.get()
            if data is None:
                message_queue.task_done()
                break
            try:
                await handle_message(data)
            except Exception:  # noqa: BLE001
                logger.exception("[RETELL-GEMINI] handle_message error call=%s", call_id)
            finally:
                message_queue.task_done()

    worker_task = asyncio.create_task(message_worker())

    try:
        async for data in websocket.iter_json():
            await message_queue.put(data)
    except WebSocketDisconnect:
        logger.info("[RETELL-GEMINI] WebSocket desconectado call_id=%s", call_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RETELL-GEMINI] error call_id=%s: %s", call_id, exc)
        try:
            await websocket.close(code=1011, reason="Server error")
        except Exception:  # noqa: BLE001
            pass
    finally:
        await message_queue.put(None)
        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            worker_task.cancel()
        mark_ws_disconnected(call_id)
        uid = resolve_call_user(call_id) or user_id
        if uid:
            try:
                from app.services.conversation_memory import finalize_voice_session_async

                finalize_voice_session_async(
                    user_id=uid,
                    session_id=call_id,
                    conversation_id=None,
                    started_at_epoch=session_started,
                )
            except Exception:  # noqa: BLE001
                pass
        release_call_user(call_id)
        logger.info("[RETELL-GEMINI] WebSocket cerrado call_id=%s", call_id)
