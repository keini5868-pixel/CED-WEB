"""Retell Custom LLM WebSocket — OpenAI GPT-4.1 como cerebro conversacional de voz."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.cognitive_intents import (
    has_advanced_confirmation,
    is_camera_voice_command,
    is_explicit_advanced_activation,
    is_meta_publish_intent,
    is_script_demo_request,
    is_web_research_intent,
)
from app.services.openai_voice_llm import OpenAIVoiceLlm
from app.services.retell_call_registry import release_call_user, resolve_call_user
from app.services.retell_custom_llm import (
    advanced_analysis_hold_phrase,
    fallback_advanced_topic,
    format_web_delivery,
    is_casual_conversation,
    is_small_talk,
    merged_user_query,
    remember_pending_script_topic,
    resolve_advanced_analysis_request,
    resolve_camera_voice_request,
    resolve_meta_publish_request,
    resolve_social_comments_request,
    resolve_web_search_request,
    is_inaudible_or_noise,
    should_clear_pending_script,
    should_execute_advanced_now,
    should_respond_to_transcript,
    is_unwanted_voice_reply,
    promised_voice_search_without_result,
    transcript_has_meta_publish_context,
    _is_concept_question,
    web_search_error_phrase,
)
from app.services.voice_llm_common import (
    is_duplicate_voice_delivery,
    normalize_voice_delivery_text,
    transcript_to_openai_messages,
)
from app.services.voice_tool_executor import execute_voice_tool
from app.services.voice_spoken import split_voice_delivery_chunks, voice_delivery_chunks
from app.services.voice_response_guard import guard_voice_response
from app.services.voice_latency import get_turn, start_turn
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance
from app.services.retell_ws_tracker import (
    active_ws_calls,
    clear_pending_advanced_topic,
    get_pending_advanced_topic,
    is_script_delivered,
    mark_greeting_sent,
    mark_script_delivered,
    mark_ws_connected,
    mark_ws_disconnected,
    note_ws_interaction,
    set_pending_advanced_topic,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["retell-custom-llm"])

POST_GREETING_COOLDOWN_S = 2.0
GREETING_FALLBACK_S = 2.0
FALLBACK_REPLY = "Disculpe, señor. Tuve un inconveniente técnico. ¿Puede repetir?"


def _turn_slot(user_key: str) -> str:
    return user_key or "_empty"


def _is_superseded_turn_rid(
    scheduled_rid: int,
    user_key: str,
    turn_latest_rid: dict[str, int],
) -> tuple[bool, int]:
    latest = turn_latest_rid.get(_turn_slot(user_key), scheduled_rid)
    return scheduled_rid < latest, latest


def _normalize_user_key(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _debounce_wait_s(user_text: str) -> float:
    words = len(user_text.split())
    if words >= 20:
        return 0.30
    if words >= 10:
        return 0.25
    return 0.15


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

    llm = OpenAIVoiceLlm()
    response_lock = asyncio.Lock()
    active_response_id = 0
    debounce_task: asyncio.Task[None] | None = None
    post_greeting_ready = asyncio.Event()
    post_greeting_ready.set()
    last_answered_user_key = ""
    last_scheduled_user_key = ""
    generation_seq = 0
    answered_response_ids: set[int] = set()
    meta_publish_guard: dict[str, float] = {}
    response_required_counts: dict[int, int] = {}
    greeting_release_task: asyncio.Task[None] | None = None
    greeting_fallback_task: asyncio.Task[None] | None = None
    turn_latest_rid: dict[str, int] = {}
    turn_draft_in_progress = False
    turn_draft_user_key = ""
    latest_incoming_rid = 0
    message_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    last_delivered_voice_content = ""
    last_web_delivery_at = 0.0
    last_web_query_norm = ""

    user_id = resolve_call_user(call_id)
    if user_id:
        llm.set_user_id(user_id)
        logger.info("[RETELL-GEMINI] user_id=%s call=%s (registry)", user_id[:8], call_id)

    from app.build_info import BUILD_VERSION
    from app.domain.openai_voice_prompt import voice_prompt_diagnostics

    prompt_diag = voice_prompt_diagnostics()
    logger.info(
        "[RETELL-GEMINI] session prompt call=%s build=%s sha=%s chars=%s ced=%s",
        call_id,
        BUILD_VERSION,
        prompt_diag.get("prompt_sha256_prefix"),
        prompt_diag.get("prompt_chars"),
        prompt_diag.get("includes_ced"),
    )

    await websocket.send_json(
        {
            "response_type": "config",
            "config": {"auto_reconnect": True, "call_details": True},
        }
    )

    greeting_sent = False
    greeting_cancelled = False
    greeting_in_flight = False

    async def cancel_greeting_stream(*, reason: str) -> None:
        nonlocal greeting_cancelled, greeting_in_flight, generation_seq
        if greeting_cancelled and not greeting_in_flight:
            return
        greeting_cancelled = True
        greeting_in_flight = False
        if greeting_fallback_task and not greeting_fallback_task.done():
            greeting_fallback_task.cancel()
        if greeting_release_task and not greeting_release_task.done():
            greeting_release_task.cancel()
        post_greeting_ready.set()
        generation_seq += 1
        logger.info("[GREETING] cancelled call=%s reason=%s gen=%s", call_id, reason, generation_seq)

    async def release_post_greeting_cooldown() -> None:
        await asyncio.sleep(POST_GREETING_COOLDOWN_S)
        post_greeting_ready.set()
        logger.info("[RETELL-GEMINI] post-greeting cooldown listo call=%s", call_id)

    async def send_greeting(response_id: int = 0, *, reason: str) -> None:
        nonlocal greeting_sent, greeting_release_task, greeting_in_flight
        if greeting_sent or greeting_cancelled:
            return
        greeting_sent = True
        greeting_in_flight = True
        post_greeting_ready.clear()
        if greeting_release_task and not greeting_release_task.done():
            greeting_release_task.cancel()
        try:
            begin_text = await llm.draft_greeting()
            if greeting_cancelled:
                post_greeting_ready.set()
                logger.info("[GREETING] aborted before send call=%s reason=%s", call_id, reason)
                return
            payload = {
                "response_type": "response",
                "response_id": response_id,
                "content": begin_text,
                "content_complete": True,
                "end_call": False,
            }
            await websocket.send_json(payload)
            mark_greeting_sent(call_id)
            greeting_release_task = asyncio.create_task(release_post_greeting_cooldown())
            logger.info(
                "[GREETING] sent call=%s reason=%s preview=%s",
                call_id,
                reason,
                begin_text[:80],
            )
        except Exception:  # noqa: BLE001
            logger.exception("[GREETING] failed call=%s reason=%s", call_id, reason)
            try:
                await websocket.send_json(
                    {
                        "response_type": "response",
                        "response_id": response_id,
                        "content": FALLBACK_REPLY,
                        "content_complete": True,
                        "end_call": False,
                    }
                )
                greeting_release_task = asyncio.create_task(release_post_greeting_cooldown())
            except Exception:  # noqa: BLE001
                logger.exception("[GREETING] fallback send failed call=%s", call_id)
                post_greeting_ready.set()
        finally:
            greeting_in_flight = False

    async def greeting_fallback() -> None:
        try:
            await asyncio.sleep(GREETING_FALLBACK_S)
            if not greeting_sent:
                await send_greeting(0, reason="fallback_timeout")
        except asyncio.CancelledError:
            return

    greeting_fallback_task = asyncio.create_task(greeting_fallback())

    async def send_voice_partial(
        *,
        response_id: int,
        content: str,
        content_complete: bool,
        generation: int | None = None,
    ) -> bool:
        if generation is not None and generation != generation_seq:
            return False
        safe, blocked = guard_voice_response(content)
        if blocked:
            logger.warning(
                "[RETELL-OPENAI] blocked partial code leak rid=%s call=%s",
                response_id,
                call_id,
            )
            safe = FALLBACK_REPLY
        payload = {
            "response_type": "response",
            "response_id": response_id,
            "content": safe or FALLBACK_REPLY,
            "content_complete": content_complete,
            "end_call": False,
        }
        await websocket.send_json(payload)
        return True

    async def send_voice_response(
        *,
        response_id: int,
        content: str,
        user_key: str,
        generation: int | None = None,
    ) -> bool:
        nonlocal active_response_id, last_answered_user_key, answered_response_ids
        nonlocal last_delivered_voice_content, last_web_delivery_at
        if generation is not None and generation != generation_seq:
            logger.info(
                "[RETELL-OPENAI] skip stale generation send rid=%s call=%s",
                response_id,
                call_id,
            )
            return False
        if response_id in answered_response_ids:
            logger.info(
                "[RETELL-OPENAI] skip duplicate send rid=%s call=%s",
                response_id,
                call_id,
            )
            return False
        safe, blocked = guard_voice_response(content)
        if blocked:
            logger.warning(
                "[RETELL-OPENAI] blocked outbound code leak rid=%s call=%s preview=%s",
                response_id,
                call_id,
                content[:80],
            )
            safe = FALLBACK_REPLY
        content = safe or FALLBACK_REPLY
        if is_duplicate_voice_delivery(last_delivered_voice_content, content):
            logger.warning(
                "[RETELL-DELIVERY] skip duplicate voice content rid=%s call=%s preview=%s",
                response_id,
                call_id,
                content[:80],
            )
            answered_response_ids.add(response_id)
            if user_key:
                last_answered_user_key = user_key
            return True
        chunks = voice_delivery_chunks(content)
        for idx, (chunk, complete) in enumerate(chunks):
            if generation is not None and generation != generation_seq:
                if idx > 0:
                    logger.warning(
                        "[CHUNK_ABORTED] rid=%s idx=%s total=%s call=%s",
                        response_id,
                        idx,
                        len(chunks),
                        call_id,
                    )
                else:
                    logger.info(
                        "[RETELL-DELIVERY] abort stale generation mid-chunk rid=%s idx=%s call=%s",
                        response_id,
                        idx,
                        call_id,
                    )
                return False
            payload = {
                "response_type": "response",
                "response_id": response_id,
                "content": chunk,
                "content_complete": complete,
                "end_call": False,
            }
            await websocket.send_json(payload)
            if idx == 0:
                turn = get_turn(call_id, response_id)
                if turn:
                    turn.mark_first_audio()
        active_response_id = max(active_response_id, response_id)
        answered_response_ids.add(response_id)
        last_delivered_voice_content = normalize_voice_delivery_text(content)
        if user_key:
            last_answered_user_key = user_key
        logger.info(
            "[RETELL-DELIVERY] complete call=%s rid=%s chars=%s chunks=%s",
            call_id,
            response_id,
            len(content),
            len(chunks),
        )
        return True

    async def handle_message(request_json: dict) -> None:
        nonlocal active_response_id, debounce_task, last_scheduled_user_key, generation_seq
        nonlocal turn_draft_in_progress, turn_draft_user_key, latest_incoming_rid

        interaction = str(request_json.get("interaction_type") or "")
        note_ws_interaction(call_id, interaction)
        logger.info("[RETELL-GEMINI] interaction=%s call=%s", interaction, call_id)

        response_id = int(request_json.get("response_id") or 0)
        if interaction == "response_required":
            response_required_counts[response_id] = response_required_counts.get(response_id, 0) + 1
            logger.info(
                "[RETELL-OPENAI] response_required rid=%s count=%s answered=%s cancelled=%s",
                response_id,
                response_required_counts[response_id],
                response_id in answered_response_ids,
                response_id < active_response_id,
            )
        if response_id in answered_response_ids:
            logger.info(
                "[RETELL-GEMINI] skip answered rid=%s call=%s",
                response_id,
                call_id,
            )
            return

        if interaction == "response_required" and response_id > 0:
            await cancel_greeting_stream(reason=f"user_turn_rid={response_id}")

        uid = resolve_call_user(call_id, request_json)
        if uid:
            llm.set_user_id(uid)
            from app.services import voice_client_session as vcs

            vcs.sync_voice_call(uid, call_id)
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
            if greeting_fallback_task and not greeting_fallback_task.done():
                greeting_fallback_task.cancel()
            await send_greeting(0, reason="call_details")
            return

        if interaction == "update_only":
            turntaking = request_json.get("turntaking")
            if turntaking:
                logger.info("[RETELL-GEMINI] turntaking=%s call=%s", turntaking, call_id)
            return

        if interaction == "reminder_required":
            transcript_raw = request_json.get("transcript") or []
            transcript = [
                Utterance(role=item.get("role", "user"), content=str(item.get("content") or ""))
                for item in transcript_raw
                if isinstance(item, dict)
            ]
            async with response_lock:
                if response_id < active_response_id:
                    return
                reminder_text = await llm.draft_reminder(transcript)
                await send_voice_response(
                    response_id=response_id,
                    content=reminder_text,
                    user_key="",
                    generation=None,
                )
            logger.info("[RETELL-GEMINI] silence ping call=%s gemini", call_id)
            return

        if interaction not in ("response_required", "reminder_required"):
            return

        transcript_raw = request_json.get("transcript") or []
        transcript = [
            Utterance(role=item.get("role", "user"), content=str(item.get("content") or ""))
            for item in transcript_raw
            if isinstance(item, dict)
        ]

        if not should_respond_to_transcript(transcript, interaction_type=interaction):
            logger.info("[RETELL-GEMINI] skip interaction=%s call=%s", interaction, call_id)
            return

        user_text = merged_user_query(transcript)
        if is_inaudible_or_noise(user_text):
            logger.info("[RETELL-GEMINI] skip inaudible/noise call=%s text=%s", call_id, user_text[:40])
            return
        if should_clear_pending_script(user_text):
            clear_pending_advanced_topic(call_id)
            llm._pending_advanced = None
        remember_pending_script_topic(
            call_id,
            transcript,
            user_text=user_text,
            set_pending=set_pending_advanced_topic,
            script_already_delivered=is_script_delivered(call_id),
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
        if user_key and last_answered_user_key and user_key != last_answered_user_key:
            if user_key.startswith(last_answered_user_key) and len(user_key) - len(last_answered_user_key) < 24:
                logger.info("[RETELL-GEMINI] skip partial extension call=%s", call_id)
                return
            if last_answered_user_key.startswith(user_key) and len(last_answered_user_key) - len(user_key) < 24:
                logger.info("[RETELL-GEMINI] skip shorter repeat call=%s", call_id)
                return

        latest_incoming_rid = max(latest_incoming_rid, response_id)
        slot = _turn_slot(user_key)
        turn_latest_rid[slot] = max(turn_latest_rid.get(slot, 0), response_id)

        generation_seq += 1
        my_generation = generation_seq

        if debounce_task and not debounce_task.done():
            debounce_task.cancel()

        last_scheduled_user_key = user_key
        wait_s = _debounce_wait_s(user_text)
        start_turn(call_id, response_id)

        async def run_debounced() -> None:
            nonlocal active_response_id, last_answered_user_key, turn_draft_in_progress, turn_draft_user_key
            scheduled_key = user_key
            scheduled_rid = response_id
            gpt_calls = 0

            def _turn_stale(rid: int = scheduled_rid) -> bool:
                stale, _ = _is_superseded_turn_rid(rid, scheduled_key, turn_latest_rid)
                return stale or my_generation != generation_seq

            async def anti_silence_if_unanswered(*, reason: str) -> None:
                """Nunca dejar response_required sin respuesta audible."""
                latest = turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid)
                if scheduled_rid in answered_response_ids:
                    return
                if my_generation != generation_seq:
                    return
                if scheduled_rid < latest:
                    return
                if is_duplicate_voice_delivery(
                    last_delivered_voice_content,
                    FALLBACK_REPLY,
                ):
                    answered_response_ids.add(scheduled_rid)
                    return
                logger.warning(
                    "[RETELL-VOICE] anti-silence rid=%s reason=%s call=%s text=%s",
                    scheduled_rid,
                    reason,
                    call_id,
                    user_text[:60],
                )
                async with response_lock:
                    await send_voice_response(
                        response_id=scheduled_rid,
                        content=FALLBACK_REPLY,
                        user_key=scheduled_key,
                        generation=my_generation,
                    )

            try:
                await post_greeting_ready.wait()
                await asyncio.sleep(wait_s)
                turn = get_turn(call_id, scheduled_rid)
                if turn:
                    turn.mark_debounce_end()
                llm.set_latency_context(call_id, scheduled_rid)
            except asyncio.CancelledError:
                return

            if my_generation != generation_seq:
                logger.info(
                    "[RETELL-TURN] rid=%s superseded=gen seq=%s current=%s gpt_calls=0 call=%s",
                    scheduled_rid,
                    my_generation,
                    generation_seq,
                    call_id,
                )
                await anti_silence_if_unanswered(reason="gen_superseded")
                return

            if scheduled_key != last_scheduled_user_key:
                logger.info("[RETELL-TURN] rid=%s superseded=debounce gpt_calls=0 call=%s", scheduled_rid, call_id)
                await anti_silence_if_unanswered(reason="debounce_superseded")
                return

            if scheduled_rid in answered_response_ids:
                logger.info(
                    "[RETELL-TURN] rid=%s superseded=answered gpt_calls=0 call=%s",
                    scheduled_rid,
                    call_id,
                )
                return

            superseded, latest_rid = _is_superseded_turn_rid(
                scheduled_rid,
                scheduled_key,
                turn_latest_rid,
            )
            if superseded:
                logger.info(
                    "[RETELL-TURN] rid=%s superseded=%s gpt_calls=0 call=%s",
                    scheduled_rid,
                    latest_rid,
                    call_id,
                )
                await anti_silence_if_unanswered(reason="turn_superseded")
                return

            pending_now = get_pending_advanced_topic(call_id)
            advanced_req = resolve_advanced_analysis_request(
                user_text,
                transcript,
                pending_topic=pending_now,
            )
            if uid:
                from app.services import voice_client_session as vcs

                if vcs.is_awaiting_instagram_caption(uid) and not is_script_demo_request(user_text):
                    advanced_req = None
            if not advanced_req and (
                has_advanced_confirmation(user_text)
                or is_explicit_advanced_activation(user_text)
            ) and not is_script_delivered(call_id):
                advanced_req = fallback_advanced_topic(transcript, pending_topic=pending_now)

            web_req = resolve_web_search_request(user_text, transcript)
            if web_req and uid:
                query_norm = " ".join(str(web_req.get("query") or "").lower().split())
                now = time.time()
                if (
                    last_web_delivery_at
                    and now - last_web_delivery_at < 15.0
                    and query_norm
                    and (
                        query_norm in last_web_query_norm
                        or last_web_query_norm in query_norm
                        or last_web_query_norm.startswith(query_norm[:24])
                        or query_norm.startswith(last_web_query_norm[:24])
                    )
                ):
                    logger.info(
                        "[RETELL-WEB] skip duplicate web query call=%s query=%s",
                        call_id,
                        query_norm[:60],
                    )
                    await anti_silence_if_unanswered(reason="web_duplicate_skip")
                    return
                clear_pending_advanced_topic(call_id)
                llm._pending_advanced = None
                kind = web_req["kind"]
                web_delivered = False
                async with response_lock:
                    if _turn_stale():
                        return
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "search_web",
                                uid,
                                {"query": web_req["query"], "kind": kind},
                            ),
                            timeout=20.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("[RETELL-GEMINI] web_search timeout call=%s", call_id)
                        tool_result = {
                            "status": "timeout",
                            "fallback": True,
                            "spoken": "Búsqueda agotada.",
                        }
                    if _turn_stale():
                        logger.info("[RETELL-GEMINI] drop stale web rid=%s", scheduled_rid)
                        return
                    if tool_result.get("fallback") or tool_result.get("status") == "timeout":
                        llm._web_search_fallback = True
                        logger.info(
                            "[RETELL-OPENAI] web_search fallback -> LLM call=%s",
                            call_id,
                        )
                    elif tool_result.get("status") == "success" or tool_result.get("ok"):
                        spoken = str(tool_result.get("spoken") or "").strip()
                        full = format_web_delivery(kind, spoken) if spoken else web_search_error_phrase(kind)
                        if not is_duplicate_voice_delivery(last_delivered_voice_content, full):
                            delivered = await send_voice_response(
                                response_id=scheduled_rid,
                                content=full,
                                user_key=scheduled_key,
                                generation=my_generation,
                            )
                            if delivered:
                                last_web_delivery_at = time.time()
                                last_web_query_norm = query_norm
                                web_delivered = True
                                logger.info(
                                    "[RETELL-GEMINI] web_search call=%s kind=%s query=%s spoken=%s",
                                    call_id,
                                    web_req["kind"],
                                    web_req["query"][:80],
                                    full[:120],
                                )
                        else:
                            logger.warning(
                                "[RETELL-WEB] skip duplicate web delivery call=%s",
                                call_id,
                            )
                            answered_response_ids.add(scheduled_rid)
                            web_delivered = True
                if web_delivered:
                    return

            # Path conversacional ligero DESACTIVADO (regresión 6f15302 — silencio post-saludo).
            # Todos los turnos usan draft_response con tools y system prompt completo.
            conversational_turn = False
            if conversational_turn:
                async with response_lock:
                    superseded, latest_rid = _is_superseded_turn_rid(
                        scheduled_rid,
                        scheduled_key,
                        turn_latest_rid,
                    )
                    if superseded:
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=%s gpt_calls=0 call=%s path=conversational",
                            scheduled_rid,
                            latest_rid,
                            call_id,
                        )
                        return
                    if scheduled_key and scheduled_key == last_answered_user_key:
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=answered_key gpt_calls=0 call=%s",
                            scheduled_rid,
                            call_id,
                        )
                        return
                    if turn_draft_in_progress and scheduled_key == turn_draft_user_key:
                        latest_for_key = turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid)
                        if scheduled_rid < latest_for_key:
                            logger.info(
                                "[RETELL-TURN] rid=%s superseded=draft_busy gpt_calls=0 call=%s",
                                scheduled_rid,
                                call_id,
                            )
                            return
                    turn_draft_in_progress = True
                    turn_draft_user_key = scheduled_key
                try:
                    conv_request = ResponseRequiredRequest(
                        interaction_type=interaction,
                        response_id=scheduled_rid,
                        transcript=transcript,
                    )
                    gpt_calls += 1
                    reply = await llm.draft_conversational_response(conv_request)
                finally:
                    turn_draft_in_progress = False
                    turn_draft_user_key = ""
                if reply and promised_voice_search_without_result(reply, user_text=user_text):
                    logger.warning(
                        "[RETELL-OPENAI] conversational search promise without tool — "
                        "escalating call=%s text=%s",
                        call_id,
                        user_text[:80],
                    )
                    reply = None
                if reply:
                    async with response_lock:
                        await send_voice_response(
                            response_id=scheduled_rid,
                            content=reply,
                            user_key=scheduled_key,
                            generation=my_generation,
                        )
                    logger.info(
                        "[RETELL-TURN] rid=%s superseded=%s gpt_calls=%s call=%s path=conversational",
                        scheduled_rid,
                        turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid),
                        gpt_calls,
                        call_id,
                    )
                    logger.info("[RETELL-GEMINI] conversational call=%s: %s", call_id, reply[:80])
                    return
                logger.warning(
                    "[RETELL-GEMINI] conversational miss — fallthrough draft_response call=%s",
                    call_id,
                )

            camera_tool = resolve_camera_voice_request(user_text)
            if camera_tool and uid:
                clear_pending_advanced_topic(call_id)
                llm._pending_advanced = None
                is_vision = camera_tool in ("analyze_camera_frame", "buscar_lo_visible")
                async with response_lock:
                    if _turn_stale():
                        return
                    if is_vision:
                        await send_voice_partial(
                            response_id=scheduled_rid,
                            content="Un momento, señor. Analizo con visión.",
                            content_complete=False,
                            generation=my_generation,
                        )
                    tool_args: dict = {}
                    if is_vision:
                        tool_args["pregunta"] = user_text
                    try:
                        cam_timeout = 10.0 if camera_tool == "request_camera_activation" else (
                            40.0 if is_vision else 12.0
                        )
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(camera_tool, uid, tool_args),
                            timeout=cam_timeout,
                        )
                    except asyncio.TimeoutError:
                        tool_result = {
                            "spoken": (
                                "No pude activar la cámara, señor. ¿Intentamos de nuevo?"
                                if camera_tool == "request_camera_activation"
                                else "No pude completar el análisis visual, señor."
                            ),
                        }
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if is_vision:
                        await send_voice_partial(
                            response_id=scheduled_rid,
                            content=spoken or "No pude analizar la imagen, señor.",
                            content_complete=True,
                            generation=my_generation,
                        )
                        active_response_id = max(active_response_id, scheduled_rid)
                        answered_response_ids.add(scheduled_rid)
                        if scheduled_key:
                            last_answered_user_key = scheduled_key
                    else:
                        await send_voice_response(
                            response_id=scheduled_rid,
                            content=spoken or "Completado, señor.",
                            user_key=scheduled_key,
                            generation=my_generation,
                        )
                logger.info("[RETELL-GEMINI] camera call=%s tool=%s", call_id, camera_tool)
                return

            meta_req = resolve_meta_publish_request(user_text, transcript)
            if meta_req and uid:
                import time as _time

                guard_key = f"{uid}:{_normalize_user_key(meta_req.get('caption') or user_text)}"
                prev = meta_publish_guard.get(guard_key, 0.0)
                if _time.time() - prev < 30.0:
                    logger.info(
                        "[RETELL-OPENAI] meta_publish skip duplicate turn call=%s key=%s",
                        call_id,
                        guard_key[:48],
                    )
                    dup_spoken = (
                        "Publicación enviada con éxito a Instagram, señor."
                        if meta_req.get("platform") == "instagram"
                        else "Publicación enviada con éxito a Facebook, señor."
                    )
                    async with response_lock:
                        await send_voice_response(
                            response_id=scheduled_rid,
                            content=dup_spoken,
                            user_key=scheduled_key,
                            generation=my_generation,
                        )
                    return
                clear_pending_advanced_topic(call_id)
                llm._pending_advanced = None
                tool_name = (
                    "publicar_instagram"
                    if meta_req["platform"] == "instagram"
                    else "publicar_facebook"
                )
                tool_args: dict = {}
                if meta_req.get("caption"):
                    if tool_name == "publicar_instagram":
                        tool_args["caption"] = meta_req["caption"]
                    else:
                        tool_args["mensaje"] = meta_req["caption"]
                tool_args["use_last_image"] = True
                async with response_lock:
                    if _turn_stale():
                        return
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(tool_name, uid, tool_args),
                            timeout=35.0,
                        )
                    except asyncio.TimeoutError:
                        tool_result = {
                            "spoken": "La publicación tardó demasiado, señor. ¿Desea que lo intente de nuevo?",
                        }
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if not spoken:
                        spoken = (
                            "No pude publicar, señor. Confirme que adjuntó la imagen en el chat."
                            if tool_name == "publicar_instagram"
                            else "No pude publicar en Facebook, señor."
                        )
                    await send_voice_response(
                        response_id=scheduled_rid,
                        content=spoken,
                        user_key=scheduled_key,
                        generation=my_generation,
                    )
                meta_publish_guard[guard_key] = _time.time()
                logger.info(
                    "[RETELL-OPENAI] meta_publish call=%s tool=%s caption=%s",
                    call_id,
                    tool_name,
                    (meta_req.get("caption") or "")[:80],
                )
                return

            comments_req = resolve_social_comments_request(user_text)
            if comments_req and uid:
                clear_pending_advanced_topic(call_id)
                llm._pending_advanced = None
                async with response_lock:
                    if _turn_stale():
                        return
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "leer_comentarios_redes",
                                uid,
                                {"platform": comments_req["platform"]},
                            ),
                            timeout=20.0,
                        )
                    except asyncio.TimeoutError:
                        tool_result = {
                            "spoken": "No pude leer los comentarios a tiempo, señor.",
                        }
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if not spoken:
                        spoken = "No pude consultar los comentarios, señor."
                    await send_voice_response(
                        response_id=scheduled_rid,
                        content=spoken,
                        user_key=scheduled_key,
                        generation=my_generation,
                    )
                logger.info(
                    "[RETELL-OPENAI] social_comments call=%s platform=%s",
                    call_id,
                    comments_req["platform"],
                )
                return

            if (
                is_explicit_advanced_activation(user_text)
                and uid
                and not is_camera_voice_command(user_text)
            ):
                topic = fallback_advanced_topic(transcript, pending_topic=pending_now) or user_text
                hold = advanced_analysis_hold_phrase()
                async with response_lock:
                    if _turn_stale():
                        return
                    await send_voice_partial(
                        response_id=scheduled_rid,
                        content=hold,
                        content_complete=False,
                        generation=my_generation,
                    )
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "consultar_claude",
                                uid,
                                {"prompt": topic},
                            ),
                            timeout=45.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("[RETELL-OPENAI] advanced timeout call=%s", call_id)
                        tool_result = {
                            "spoken": (
                                "El sistema avanzado tardó demasiado, señor. "
                                "¿Desea que lo intente de nuevo?"
                            ),
                        }
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if not spoken:
                        chunks = [("Disculpe, señor. No pude completar el análisis avanzado.", True)]
                    else:
                        chunks = voice_delivery_chunks(spoken)
                    for chunk, complete in chunks:
                        if my_generation != generation_seq:
                            return
                        await send_voice_partial(
                            response_id=scheduled_rid,
                            content=chunk,
                            content_complete=complete,
                            generation=my_generation,
                        )
                    active_response_id = max(active_response_id, scheduled_rid)
                    answered_response_ids.add(scheduled_rid)
                    if scheduled_key:
                        last_answered_user_key = scheduled_key
                    clear_pending_advanced_topic(call_id)
                    llm._pending_advanced = None
                logger.info(
                    "[RETELL-OPENAI] advanced explicit call=%s topic=%s",
                    call_id,
                    topic[:80],
                )
                return

            request = ResponseRequiredRequest(
                interaction_type=interaction,  # type: ignore[arg-type]
                response_id=scheduled_rid,
                transcript=transcript,
            )

            async with response_lock:
                superseded, latest_rid = _is_superseded_turn_rid(
                    scheduled_rid,
                    scheduled_key,
                    turn_latest_rid,
                )
                if superseded:
                    logger.info(
                        "[RETELL-TURN] rid=%s superseded=%s gpt_calls=0 call=%s path=draft",
                        scheduled_rid,
                        latest_rid,
                        call_id,
                    )
                    return
                if scheduled_key and scheduled_key == last_answered_user_key:
                    logger.info(
                        "[RETELL-TURN] rid=%s superseded=answered_key gpt_calls=0 call=%s",
                        scheduled_rid,
                        call_id,
                    )
                    return
                if turn_draft_in_progress and scheduled_key == turn_draft_user_key:
                    latest_for_key = turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid)
                    if scheduled_rid < latest_for_key:
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=draft_busy gpt_calls=0 call=%s",
                            scheduled_rid,
                            call_id,
                        )
                        return
                turn_draft_in_progress = True
                turn_draft_user_key = scheduled_key

            try:
                gpt_calls += 1
                async with response_lock:
                    superseded_now, latest_now = _is_superseded_turn_rid(
                        scheduled_rid,
                        scheduled_key,
                        turn_latest_rid,
                    )
                    if superseded_now:
                        await anti_silence_if_unanswered(reason="draft_superseded")
                        return

                    try:
                        final_event = None
                        async for event in llm.draft_response(request):
                            stale, _ = _is_superseded_turn_rid(
                                scheduled_rid,
                                scheduled_key,
                                turn_latest_rid,
                            )
                            if stale or my_generation != generation_seq:
                                logger.info(
                                    "[RETELL-TURN] rid=%s superseded=%s gpt_calls=%s call=%s path=draft_abort",
                                    scheduled_rid,
                                    turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid),
                                    gpt_calls,
                                    call_id,
                                )
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
                                    regen = await llm.generate_natural_reply(
                                        messages=transcript_to_openai_messages(transcript),
                                        user_text=user_text,
                                        overlay=(
                                            "Responde de forma natural y breve usando tu conocimiento. "
                                            "NUNCA cites 'Conocimiento interno CED' ni etiquetas [Marketing digital]."
                                        ),
                                        path="concept_kb_regen",
                                        max_tokens=640,
                                    )
                                    content = regen or FALLBACK_REPLY
                                elif is_casual_conversation(user_text):
                                    reformed = await llm.generate_empathetic_reformulation(
                                        user_text,
                                        transcript=transcript,
                                        bad_reply=content,
                                    )
                                    if reformed:
                                        content = reformed
                                    else:
                                        conv = await llm.draft_conversational_response(request)
                                        if conv:
                                            content = conv
                                else:
                                    content = FALLBACK_REPLY
                            await send_voice_response(
                                response_id=scheduled_rid,
                                content=content,
                                user_key=scheduled_key,
                                generation=my_generation,
                            )
                        elif not superseded_now:
                            logger.warning(
                                "[RETELL-GEMINI] empty draft_response call=%s rid=%s text=%s",
                                call_id,
                                scheduled_rid,
                                user_text[:80],
                            )
                            await send_voice_response(
                                response_id=scheduled_rid,
                                content=FALLBACK_REPLY,
                                user_key=scheduled_key,
                                generation=my_generation,
                            )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[RETELL-GEMINI] draft_response error call=%s last=%s",
                            call_id,
                            user_text[:80],
                        )
                        await send_voice_response(
                            response_id=scheduled_rid,
                            content=FALLBACK_REPLY,
                            user_key=scheduled_key,
                            generation=my_generation,
                        )
            finally:
                turn_draft_in_progress = False
                turn_draft_user_key = ""
                await anti_silence_if_unanswered(reason="draft_finally")
                logger.info(
                    "[RETELL-TURN] rid=%s superseded=%s gpt_calls=%s call=%s path=draft",
                    scheduled_rid,
                    turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid),
                    gpt_calls,
                    call_id,
                )

            await anti_silence_if_unanswered(reason="run_debounced_tail")

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
                from app.services import voice_client_session as vcs

                vcs.end_voice_publish_session(uid, call_id)
            except Exception:  # noqa: BLE001
                pass
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