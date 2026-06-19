"""Retell Custom LLM WebSocket — Gemini 2.5 Pro como cerebro de voz."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.cognitive_intents import (
    has_advanced_confirmation,
    is_explicit_advanced_activation,
    is_script_demo_request,
)
from app.services.gemini_voice_llm import GeminiVoiceLlm, draft_begin_message
from app.services.retell_call_registry import release_call_user, resolve_call_user
from app.services.retell_custom_llm import (
    advanced_analysis_hold_phrase,
    concise_reply_for_small_talk,
    fallback_advanced_topic,
    format_web_delivery,
    is_small_talk,
    merged_user_query,
    remember_pending_script_topic,
    resolve_advanced_analysis_request,
    resolve_web_search_request,
    should_execute_advanced_now,
    should_respond_to_transcript,
    is_unwanted_voice_reply,
    _is_concept_question,
    web_search_error_phrase,
)
from app.services.voice_tool_executor import execute_voice_tool
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance
from app.services.retell_ws_tracker import (
    active_ws_calls,
    clear_pending_advanced_topic,
    get_pending_advanced_topic,
    mark_greeting_sent,
    mark_ws_connected,
    mark_ws_disconnected,
    note_ws_interaction,
    set_pending_advanced_topic,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["retell-custom-llm"])

POST_GREETING_COOLDOWN_S = 2.0
FALLBACK_REPLY = "Disculpe, señor. Tuve un inconveniente. ¿Puede repetir?"
REMINDER_REPLY = "Sigo atento, señor. ¿Continuamos?"


def _normalize_user_key(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _debounce_wait_s(user_text: str) -> float:
    words = len(user_text.split())
    if words >= 20:
        return 0.70
    if words >= 10:
        return 0.55
    return 0.35


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
    post_greeting_ready = asyncio.Event()
    post_greeting_ready.set()
    last_answered_user_key = ""
    last_scheduled_user_key = ""
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

    async def send_voice_partial(
        *,
        response_id: int,
        content: str,
        content_complete: bool,
    ) -> None:
        payload = {
            "response_type": "response",
            "response_id": response_id,
            "content": content,
            "content_complete": content_complete,
            "end_call": False,
        }
        await websocket.send_json(payload)

    async def send_voice_response(
        *,
        response_id: int,
        content: str,
        user_key: str,
    ) -> bool:
        nonlocal active_response_id, last_answered_user_key
        if response_id < active_response_id:
            return False
        payload = {
            "response_type": "response",
            "response_id": response_id,
            "content": content,
            "content_complete": True,
            "end_call": False,
        }
        await websocket.send_json(payload)
        active_response_id = response_id
        if user_key:
            last_answered_user_key = user_key
        logger.info(
            "[RETELL-GEMINI] respuesta enviada call=%s rid=%s chars=%s",
            call_id,
            response_id,
            len(content),
        )
        return True

    async def handle_message(request_json: dict) -> None:
        nonlocal active_response_id, debounce_task, last_scheduled_user_key

        interaction = str(request_json.get("interaction_type") or "")
        note_ws_interaction(call_id, interaction)
        logger.info("[RETELL-GEMINI] interaction=%s call=%s", interaction, call_id)

        uid = resolve_call_user(call_id, request_json)
        if uid:
            llm.set_user_id(uid)
            pending_for_llm = get_pending_advanced_topic(call_id)
            if pending_for_llm:
                llm._pending_advanced = pending_for_llm

        if interaction == "ping_pong":
            await websocket.send_json(
                {
                    "response_type": "ping_pong",
                    "timestamp": request_json.get("timestamp"),
                }
            )
            return

        if interaction == "call_details":
            logger.info("[RETELL-GEMINI] call_details call=%s (saludo ya enviado)", call_id)
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

        if interaction == "reminder_required":
            logger.info("[RETELL-GEMINI] skip reminder call=%s", call_id)
            return

        if not should_respond_to_transcript(transcript, interaction_type=interaction):
            logger.info("[RETELL-GEMINI] skip interaction=%s call=%s", interaction, call_id)
            return

        user_text = merged_user_query(transcript)
        remember_pending_script_topic(
            call_id,
            transcript,
            user_text=user_text,
            set_pending=set_pending_advanced_topic,
        )
        user_key = _normalize_user_key(user_text)
        pending_topic = get_pending_advanced_topic(call_id)
        advanced_preview = resolve_advanced_analysis_request(
            user_text,
            transcript,
            pending_topic=pending_topic,
        )
        if user_key and user_key == last_answered_user_key:
            if not (
                advanced_preview
                or has_advanced_confirmation(user_text)
                or is_explicit_advanced_activation(user_text)
            ):
                logger.info("[RETELL-GEMINI] skip duplicate user turn call=%s", call_id)
                return

        active_response_id = max(active_response_id, response_id)

        if debounce_task and not debounce_task.done() and user_key != last_scheduled_user_key:
            debounce_task.cancel()

        last_scheduled_user_key = user_key
        wait_s = _debounce_wait_s(user_text)

        async def run_debounced() -> None:
            nonlocal active_response_id, last_answered_user_key
            try:
                await post_greeting_ready.wait()
                await asyncio.sleep(wait_s)
            except asyncio.CancelledError:
                return

            if response_id < active_response_id:
                logger.info(
                    "[RETELL-GEMINI] skip stale rid=%s active=%s",
                    response_id,
                    active_response_id,
                )
                return

            pending_now = get_pending_advanced_topic(call_id)
            advanced_req = resolve_advanced_analysis_request(
                user_text,
                transcript,
                pending_topic=pending_now,
            )
            if not advanced_req and (
                has_advanced_confirmation(user_text)
                or is_explicit_advanced_activation(user_text)
            ):
                advanced_req = fallback_advanced_topic(transcript, pending_topic=pending_now)

            if is_small_talk(user_text, transcript) and not resolve_web_search_request(
                user_text, transcript
            ) and not advanced_req:
                reply = concise_reply_for_small_talk(user_text, transcript)
                async with response_lock:
                    await send_voice_response(
                        response_id=response_id,
                        content=reply,
                        user_key=user_key,
                    )
                logger.info("[RETELL-GEMINI] small_talk call=%s: %s", call_id, reply)
                return

            web_req = resolve_web_search_request(user_text, transcript)
            if web_req and uid:
                kind = web_req["kind"]
                async with response_lock:
                    if response_id < active_response_id:
                        return
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "search_web",
                                uid,
                                {"query": web_req["query"], "kind": kind},
                            ),
                            timeout=28.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("[RETELL-GEMINI] web_search timeout call=%s", call_id)
                        tool_result = {"spoken": web_search_error_phrase(kind)}
                    if response_id < active_response_id:
                        logger.info("[RETELL-GEMINI] drop stale web rid=%s", response_id)
                        return
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if not spoken or spoken.startswith("No fue posible"):
                        full = web_search_error_phrase(kind)
                    else:
                        full = format_web_delivery(kind, spoken)
                    await send_voice_response(
                        response_id=response_id,
                        content=full,
                        user_key=user_key,
                    )
                logger.info(
                    "[RETELL-GEMINI] web_search call=%s kind=%s query=%s spoken=%s",
                    call_id,
                    web_req["kind"],
                    web_req["query"][:80],
                    full[:120],
                )
                return

            if advanced_req and is_script_demo_request(advanced_req):
                set_pending_advanced_topic(call_id, advanced_req)
                llm._pending_advanced = advanced_req
            if advanced_req and uid and should_execute_advanced_now(user_text, advanced_req):
                hold = advanced_analysis_hold_phrase()
                async with response_lock:
                    if response_id < active_response_id:
                        return
                    await send_voice_partial(
                        response_id=response_id,
                        content=hold,
                        content_complete=False,
                    )
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "consultar_claude",
                                uid,
                                {"prompt": advanced_req},
                            ),
                            timeout=45.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("[RETELL-GEMINI] advanced timeout call=%s", call_id)
                        tool_result = {
                            "spoken": (
                                "El sistema avanzado tardó demasiado, señor. "
                                "¿Desea que lo intente de nuevo?"
                            ),
                        }
                    if response_id < active_response_id:
                        logger.info("[RETELL-GEMINI] drop stale advanced rid=%s", response_id)
                        return
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if not spoken or spoken.startswith("No fue posible"):
                        full = (
                            spoken
                            or "Disculpe, señor. No pude completar el análisis avanzado."
                        )
                    else:
                        from app.services.voice_spoken import fit_voice_spoken, voice_spoken_limit

                        full = fit_voice_spoken(spoken, max_chars=voice_spoken_limit(advanced_req))
                    if response_id < active_response_id:
                        return
                    await send_voice_partial(
                        response_id=response_id,
                        content=full,
                        content_complete=True,
                    )
                    active_response_id = response_id
                    if user_key:
                        last_answered_user_key = user_key
                    clear_pending_advanced_topic(call_id)
                    llm._pending_advanced = None
                logger.info(
                    "[RETELL-GEMINI] advanced call=%s topic=%s chars=%s",
                    call_id,
                    advanced_req[:80],
                    len(spoken),
                )
                return

            if (
                has_advanced_confirmation(user_text)
                or is_explicit_advanced_activation(user_text)
            ) and uid:
                topic = fallback_advanced_topic(transcript, pending_topic=pending_now)
                logger.warning(
                    "[RETELL-GEMINI] confirm sin ruta advanced — forzando topic=%s",
                    topic[:80],
                )
                advanced_req = topic
                if should_execute_advanced_now(user_text, advanced_req):
                    hold = advanced_analysis_hold_phrase()
                    async with response_lock:
                        if response_id < active_response_id:
                            return
                        await send_voice_partial(
                            response_id=response_id,
                            content=hold,
                            content_complete=False,
                        )
                        try:
                            tool_result = await asyncio.wait_for(
                                execute_voice_tool(
                                    "consultar_claude",
                                    uid,
                                    {"prompt": advanced_req},
                                ),
                                timeout=45.0,
                            )
                        except asyncio.TimeoutError:
                            tool_result = {
                                "spoken": (
                                    "El sistema avanzado tardó demasiado, señor. "
                                    "¿Desea que lo intente de nuevo?"
                                ),
                            }
                        spoken = str(tool_result.get("spoken") or "").strip()
                        full = spoken or "Disculpe, señor. No pude completar el análisis."
                        await send_voice_partial(
                            response_id=response_id,
                            content=full,
                            content_complete=True,
                        )
                        active_response_id = response_id
                        if user_key:
                            last_answered_user_key = user_key
                        clear_pending_advanced_topic(call_id)
                        llm._pending_advanced = None
                    return

            request = ResponseRequiredRequest(
                interaction_type=interaction,  # type: ignore[arg-type]
                response_id=response_id,
                transcript=transcript,
            )

            async with response_lock:
                if response_id < active_response_id:
                    return

                try:
                    final_event = None
                    async for event in llm.draft_response(request):
                        if event.response_id < active_response_id:
                            break
                        final_event = event
                    if final_event is not None:
                        content = (final_event.content or "").strip() or FALLBACK_REPLY
                        if is_unwanted_voice_reply(content, user_text=user_text):
                            logger.warning(
                                "[RETELL-GEMINI] bloqueado relleno chatbot call=%s text=%s reply=%s",
                                call_id,
                                user_text[:60],
                                content[:80],
                            )
                            if (
                                has_advanced_confirmation(user_text)
                                or is_explicit_advanced_activation(user_text)
                            ) and uid:
                                topic = fallback_advanced_topic(
                                    transcript,
                                    pending_topic=get_pending_advanced_topic(call_id),
                                )
                                tool_result = await asyncio.wait_for(
                                    execute_voice_tool(
                                        "consultar_claude",
                                        uid,
                                        {"prompt": topic},
                                    ),
                                    timeout=45.0,
                                )
                                content = str(tool_result.get("spoken") or "").strip() or FALLBACK_REPLY
                            elif _is_concept_question(user_text):
                                from app.services.internal_knowledge import (
                                    format_hits_for_prompt,
                                    search_internal_knowledge,
                                )

                                hits = search_internal_knowledge(user_text, limit=2)
                                if hits:
                                    content = format_hits_for_prompt(hits)
                                else:
                                    content = FALLBACK_REPLY
                            else:
                                content = FALLBACK_REPLY
                        await send_voice_response(
                            response_id=response_id,
                            content=content,
                            user_key=user_key,
                        )
                    elif response_id >= active_response_id:
                        logger.warning(
                            "[RETELL-GEMINI] empty draft_response call=%s rid=%s text=%s",
                            call_id,
                            response_id,
                            user_text[:80],
                        )
                        await send_voice_response(
                            response_id=response_id,
                            content=FALLBACK_REPLY,
                            user_key=user_key,
                        )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "[RETELL-GEMINI] draft_response error call=%s last=%s",
                        call_id,
                        user_text[:80],
                    )
                    await send_voice_response(
                        response_id=response_id,
                        content=FALLBACK_REPLY,
                        user_key=user_key,
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
