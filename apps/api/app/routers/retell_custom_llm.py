"""Retell Custom LLM WebSocket — Gemini 2.5 Flash como cerebro conversacional de voz."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.cognitive_intents import (
    is_camera_voice_command,
    is_meta_publish_intent,
    is_script_demo_request,
    is_web_research_intent,
)
from app.services.gemini_voice_llm import GeminiVoiceLlm
from app.services.retell_call_registry import release_call_user, resolve_call_user
from app.services.retell_custom_llm import (
    format_web_delivery,
    is_casual_conversation,
    is_small_talk,
    merged_user_query,
    remember_pending_script_topic,
    resolve_camera_voice_request,
    resolve_meta_publish_request,
    resolve_social_comments_request,
    resolve_web_search_request,
    is_inaudible_or_noise,
    should_clear_pending_script,
    should_respond_to_transcript,
    is_unwanted_voice_reply,
    promised_voice_search_without_result,
    web_search_hold_phrase,
    _is_concept_question,
    web_search_error_phrase,
)
from app.services.navigation_voice_intent import (
    normalize_navigation_query,
    resolve_navigation_confirm,
    resolve_navigation_place_search,
    resolve_open_map_request,
)
from app.services.voice_llm_common import (
    FALLBACK_REPLY,
    WEB_SEARCH_VOICE_FALLBACK,
    is_duplicate_voice_delivery,
    normalize_voice_delivery_text,
)
from app.services.voice_tool_executor import NAVIGATION_TIMEOUT_SEC, execute_voice_tool
from app.services.voice_spoken import (
    finalize_voice_delivery_text,
    split_voice_delivery_chunks,
    voice_delivery_chunks,
)
from app.services.voice_response_guard import guard_voice_response
from app.services.voice_latency import get_turn, start_turn
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance
from app.services.retell_ws_tracker import (
    active_ws_calls,
    clear_pending_advanced_topic,
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

POST_GREETING_COOLDOWN_S = 0.35
GREETING_FALLBACK_S = 2.0
WEB_SEARCH_FAST_PATH_TIMEOUT_SEC = 15.0


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
        return 0.22
    if words >= 10:
        return 0.18
    return 0.10


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
            if not post_greeting_ready.is_set():
                post_greeting_ready.set()
                logger.info("[RETELL-GEMINI] post-greeting ready forced call=%s", call_id)

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
        content = finalize_voice_delivery_text(content)
        if not content:
            content = FALLBACK_REPLY
        if is_duplicate_voice_delivery(last_delivered_voice_content, content):
            logger.warning(
                "[RETELL-DELIVERY] skip duplicate voice content rid=%s call=%s preview=%s",
                response_id,
                call_id,
                content[:80],
            )
            await websocket.send_json(
                {
                    "response_type": "response",
                    "response_id": response_id,
                    "content": "",
                    "content_complete": True,
                    "end_call": False,
                }
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

    async def ack_empty_response(*, response_id: int, reason: str) -> None:
        """Retell exige content_complete=True en cada response_required, aunque no hablemos."""
        nonlocal answered_response_ids
        if response_id in answered_response_ids:
            return
        async with response_lock:
            if response_id in answered_response_ids:
                return
            await websocket.send_json(
                {
                    "response_type": "response",
                    "response_id": response_id,
                    "content": "",
                    "content_complete": True,
                    "end_call": False,
                }
            )
            answered_response_ids.add(response_id)
        logger.info(
            "[RETELL-GEMINI] ack_empty rid=%s reason=%s call=%s",
            response_id,
            reason,
            call_id,
        )

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
            if interaction == "response_required":
                await ack_empty_response(response_id=response_id, reason="duplicate_rid")
            return

        if interaction == "response_required" and response_id > 0:
            await cancel_greeting_stream(reason=f"user_turn_rid={response_id}")

        uid = resolve_call_user(call_id, request_json)
        if uid:
            llm.set_user_id(uid)
            from app.services import voice_client_session as vcs

            vcs.sync_voice_call(uid, call_id)

        if interaction == "ping_pong":
            uid = resolve_call_user(call_id, request_json)
            if uid:
                from app.services.navigation_voice import pop_navigation_speech

                nav_text = pop_navigation_speech(uid)
                if nav_text:
                    await websocket.send_json(
                        {
                            "response_type": "agent_interrupt",
                            "content": nav_text,
                            "interrupt_prior_spoke_content": False,
                        }
                    )
                    logger.info(
                        "[RETELL-GEMINI] navigation agent_interrupt call=%s text=%s",
                        call_id,
                        nav_text[:80],
                    )
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
            logger.info(
                "[RETELL-GEMINI] skip interaction=%s call=%s text=%s",
                interaction,
                call_id,
                merged_user_query(transcript)[:60],
            )
            if interaction == "response_required":
                await ack_empty_response(response_id=response_id, reason="should_respond_false")
            return

        user_text = merged_user_query(transcript)
        if is_inaudible_or_noise(user_text):
            logger.info("[RETELL-GEMINI] skip inaudible/noise call=%s text=%s", call_id, user_text[:40])
            if interaction == "response_required":
                await ack_empty_response(response_id=response_id, reason="inaudible")
            return
        if should_clear_pending_script(user_text):
            clear_pending_advanced_topic(call_id)
        remember_pending_script_topic(
            call_id,
            transcript,
            user_text=user_text,
            set_pending=set_pending_advanced_topic,
            script_already_delivered=is_script_delivered(call_id),
        )
        user_key = _normalize_user_key(user_text)
        pending_web = resolve_web_search_request(user_text, transcript)
        if user_key and user_key == last_answered_user_key and not pending_web:
            logger.info("[RETELL-GEMINI] skip duplicate user turn call=%s", call_id)
            await ack_empty_response(response_id=response_id, reason="duplicate_user_key")
            return
        if (
            pending_web
            and user_key
            and last_answered_user_key
            and user_key == last_answered_user_key
        ):
            logger.info(
                "[RETELL-GEMINI] repeat web query after prior answer call=%s",
                call_id,
            )
        elif user_key and last_answered_user_key and user_key != last_answered_user_key:
            if not pending_web and user_key.startswith(last_answered_user_key) and len(user_key) - len(last_answered_user_key) < 24:
                logger.info("[RETELL-GEMINI] skip partial extension call=%s", call_id)
                await ack_empty_response(response_id=response_id, reason="partial_extension")
                return
            if not pending_web and last_answered_user_key.startswith(user_key) and len(last_answered_user_key) - len(user_key) < 24:
                logger.info("[RETELL-GEMINI] skip shorter repeat call=%s", call_id)
                await ack_empty_response(response_id=response_id, reason="shorter_repeat")
                return

        latest_incoming_rid = max(latest_incoming_rid, response_id)
        slot = _turn_slot(user_key)
        turn_latest_rid[slot] = max(turn_latest_rid.get(slot, 0), response_id)

        if user_key != last_scheduled_user_key:
            generation_seq += 1
        my_generation = generation_seq

        if debounce_task and not debounce_task.done():
            debounce_task.cancel()

        last_scheduled_user_key = user_key
        wait_s = _debounce_wait_s(user_text)
        start_turn(call_id, response_id)

        logger.info(
            "[RETELL-TURN] schedule rid=%s call=%s text=%s key=%s",
            response_id,
            call_id,
            user_text[:80],
            user_key[:48],
        )

        async def run_debounced() -> None:
            nonlocal active_response_id, last_answered_user_key, turn_draft_in_progress, turn_draft_user_key
            scheduled_key = user_key
            scheduled_rid = response_id
            gpt_calls = 0
            partial_sent = False

            def _turn_rid_stale(rid: int = scheduled_rid) -> bool:
                stale, _ = _is_superseded_turn_rid(rid, scheduled_key, turn_latest_rid)
                return stale

            def _turn_stale(rid: int = scheduled_rid) -> bool:
                return _turn_rid_stale(rid) or my_generation != generation_seq

            def _can_deliver_turn(rid: int = scheduled_rid) -> bool:
                if rid in answered_response_ids:
                    return False
                latest = turn_latest_rid.get(_turn_slot(scheduled_key), rid)
                return rid >= latest

            async def deliver_voice(content: str, *, rid: int = scheduled_rid) -> bool:
                if not _can_deliver_turn(rid):
                    return False
                async with response_lock:
                    return await send_voice_response(
                        response_id=rid,
                        content=content,
                        user_key=scheduled_key,
                        generation=None,
                    )

            async def anti_silence_if_unanswered(*, reason: str) -> None:
                """Nunca dejar response_required sin respuesta audible."""
                if scheduled_rid in answered_response_ids:
                    return
                if _turn_rid_stale():
                    await ack_empty_response(
                        response_id=scheduled_rid,
                        reason=f"{reason}_stale",
                    )
                    return
                if not _can_deliver_turn():
                    await ack_empty_response(
                        response_id=scheduled_rid,
                        reason=f"{reason}_stale_rid",
                    )
                    return
                fallback_content = WEB_SEARCH_VOICE_FALLBACK if pending_web else FALLBACK_REPLY
                if is_duplicate_voice_delivery(
                    last_delivered_voice_content,
                    fallback_content,
                ):
                    await ack_empty_response(
                        response_id=scheduled_rid,
                        reason=f"{reason}_duplicate_fallback",
                    )
                    return
                logger.warning(
                    "[RETELL-VOICE] anti-silence rid=%s reason=%s call=%s text=%s",
                    scheduled_rid,
                    reason,
                    call_id,
                    user_text[:60],
                )
                await deliver_voice(fallback_content)

            async def ack_superseded_turn(*, reason: str) -> None:
                """Turno reemplazado por uno más nuevo — no hablar fallback."""
                if scheduled_rid in answered_response_ids:
                    return
                await ack_empty_response(response_id=scheduled_rid, reason=reason)

            async def complete_partial_or_deliver(content: str) -> bool:
                nonlocal partial_sent
                partial_sent = False
                return await deliver_voice(content)

            try:
                try:
                    await asyncio.wait_for(post_greeting_ready.wait(), timeout=8.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        "[RETELL-GEMINI] post-greeting wait timeout rid=%s call=%s",
                        scheduled_rid,
                        call_id,
                    )
                    post_greeting_ready.set()
                await asyncio.sleep(wait_s)
                turn = get_turn(call_id, scheduled_rid)
                if turn:
                    turn.mark_debounce_end()
                llm.set_latency_context(call_id, scheduled_rid)
            except asyncio.CancelledError:
                return

            if my_generation != generation_seq and scheduled_key != last_scheduled_user_key:
                logger.info(
                    "[RETELL-TURN] rid=%s superseded=gen seq=%s current=%s gpt_calls=0 call=%s",
                    scheduled_rid,
                    my_generation,
                    generation_seq,
                    call_id,
                )
                await ack_superseded_turn(reason="gen_superseded")
                return

            if scheduled_key != last_scheduled_user_key:
                logger.info("[RETELL-TURN] rid=%s superseded=debounce gpt_calls=0 call=%s", scheduled_rid, call_id)
                await ack_superseded_turn(reason="debounce_superseded")
                return

            if scheduled_rid in answered_response_ids:
                logger.info(
                    "[RETELL-TURN] rid=%s superseded=answered gpt_calls=0 call=%s",
                    scheduled_rid,
                    call_id,
                )
                return

            conversational_turn = is_small_talk(user_text, transcript)

            nav_req = resolve_navigation_place_search(user_text, transcript)
            if nav_req and uid:
                query = normalize_navigation_query(str(nav_req.get("query") or ""))
                if query:
                    try:
                        if resolve_open_map_request(user_text) or nav_req.get("open_map"):
                            open_result = await execute_voice_tool(
                                "activar_modo_conducir",
                                uid,
                                {},
                            )
                            spoken_open = str(open_result.get("spoken") or "").strip()
                        else:
                            spoken_open = ""

                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "search_nearby_places",
                                uid,
                                {"query": query, "place": query, "destino": query},
                            ),
                            timeout=20.0,
                        )
                        spoken = str(tool_result.get("spoken") or "").strip()
                        if not spoken:
                            spoken = f"No encontré {query} cerca, señor."
                        if spoken_open and not tool_result.get("ok"):
                            spoken = spoken_open
                        elif spoken_open and tool_result.get("ok"):
                            spoken = spoken

                        if _turn_rid_stale():
                            await ack_superseded_turn(reason="nav_stale")
                            return
                        delivered = await complete_partial_or_deliver(spoken)
                        if not delivered:
                            await anti_silence_if_unanswered(reason="nav_deliver_failed")
                        logger.info(
                            "[RETELL-GEMINI] nav fast-path call=%s query=%s ok=%s",
                            call_id,
                            query[:40],
                            tool_result.get("ok"),
                        )
                        return
                    except asyncio.TimeoutError:
                        logger.warning("[RETELL-GEMINI] nav search timeout call=%s", call_id)
                        await complete_partial_or_deliver(
                            "Señor, la búsqueda en el mapa tardó demasiado. ¿Repito el lugar?"
                        )
                        return
                    except Exception:
                        logger.exception("[RETELL-GEMINI] nav fast-path failed call=%s", call_id)

            nav_confirm = resolve_navigation_confirm(user_text, transcript, user_id=uid)
            if nav_confirm and uid:
                try:
                    action = str(nav_confirm.get("action") or "")
                    if action == "begin_navigation":
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool("start_navigation", uid, {}),
                            timeout=NAVIGATION_TIMEOUT_SEC,
                        )
                    else:
                        idx = int(nav_confirm.get("index") or 0)
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "start_navigation",
                                uid,
                                {"index": idx},
                            ),
                            timeout=NAVIGATION_TIMEOUT_SEC,
                        )
                    spoken = str(tool_result.get("spoken") or "Iniciando ruta, señor.").strip()
                    if _turn_rid_stale():
                        await ack_superseded_turn(reason="nav_confirm_stale")
                        return
                    delivered = await complete_partial_or_deliver(spoken)
                    if not delivered:
                        await anti_silence_if_unanswered(reason="nav_confirm_deliver_failed")
                    logger.info(
                        "[RETELL-GEMINI] nav confirm fast-path call=%s action=%s ok=%s",
                        call_id,
                        action,
                        tool_result.get("ok"),
                    )
                    return
                except asyncio.TimeoutError:
                    logger.warning("[RETELL-GEMINI] nav confirm timeout call=%s", call_id)
                    await complete_partial_or_deliver(
                        "Señor, calcular la ruta tardó demasiado. ¿Repito?"
                    )
                    return
                except Exception:
                    logger.exception("[RETELL-GEMINI] nav confirm fast-path failed call=%s", call_id)

            if resolve_open_map_request(user_text) and uid and not nav_req:
                try:
                    tool_result = await execute_voice_tool("activar_modo_conducir", uid, {})
                    spoken = str(tool_result.get("spoken") or "Abro el mapa, señor.").strip()
                    if _turn_rid_stale():
                        await ack_superseded_turn(reason="open_map_stale")
                        return
                    await complete_partial_or_deliver(spoken)
                    return
                except Exception:
                    logger.exception("[RETELL-GEMINI] open map fast-path failed call=%s", call_id)

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
                await ack_superseded_turn(reason="turn_superseded")
                return

            web_req = resolve_web_search_request(user_text, transcript)
            if web_req and uid:

                async def handle_web_search_voice(
                    *,
                    web_req: dict[str, str],
                    query_norm: str,
                ) -> None:
                    """Fast-path search_web — SIEMPRE cierra el turno con voz audible."""
                    nonlocal partial_sent, last_web_delivery_at, last_web_query_norm
                    kind = str(web_req.get("kind") or "general")
                    query = str(web_req.get("query") or user_text).strip()

                    async def finish_web_voice(content: str, *, reason: str) -> None:
                        nonlocal last_web_delivery_at, last_web_query_norm
                        safe = (content or WEB_SEARCH_VOICE_FALLBACK).strip() or WEB_SEARCH_VOICE_FALLBACK
                        if _turn_rid_stale():
                            logger.info(
                                "[RETELL-GEMINI] web stale at finish rid=%s reason=%s call=%s",
                                scheduled_rid,
                                reason,
                                call_id,
                            )
                            await complete_partial_or_deliver(WEB_SEARCH_VOICE_FALLBACK)
                            return
                        delivered = await complete_partial_or_deliver(safe)
                        if delivered:
                            last_web_delivery_at = time.time()
                            last_web_query_norm = query_norm
                            logger.info(
                                "[RETELL-GEMINI] web_search call=%s kind=%s reason=%s spoken=%s",
                                call_id,
                                kind,
                                reason,
                                safe[:120],
                            )
                        else:
                            logger.warning(
                                "[RETELL-GEMINI] web_search deliver failed rid=%s call=%s reason=%s",
                                scheduled_rid,
                                call_id,
                                reason,
                            )
                            await anti_silence_if_unanswered(reason=f"web_finish_{reason}")

                    try:
                        tool_result: dict[str, Any]
                        try:
                            tool_result = await asyncio.wait_for(
                                execute_voice_tool(
                                    "search_web",
                                    uid,
                                    {"query": query, "kind": kind},
                                ),
                                timeout=WEB_SEARCH_FAST_PATH_TIMEOUT_SEC,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                "[RETELL-GEMINI] web_search timeout call=%s query=%s",
                                call_id,
                                query[:80],
                            )
                            await finish_web_voice(
                                "Señor, la búsqueda tardó demasiado. "
                                "¿Desea que lo intente de nuevo?",
                                reason="timeout",
                            )
                            return
                        except Exception:
                            logger.exception(
                                "[RETELL-GEMINI] web_search error call=%s query=%s",
                                call_id,
                                query[:80],
                            )
                            await finish_web_voice(
                                "Disculpe señor, tuve un inconveniente buscando. "
                                "¿Puede repetir la pregunta?",
                                reason="error",
                            )
                            return

                        if tool_result.get("status") == "success" or tool_result.get("ok"):
                            spoken = str(tool_result.get("spoken") or "").strip()
                            if spoken:
                                delivery = format_web_delivery(kind, spoken)
                                if not is_unwanted_voice_reply(delivery, user_text=user_text):
                                    await finish_web_voice(delivery, reason="success")
                                    return
                                logger.warning(
                                    "[RETELL-WEB] discard internal kb leak in web result call=%s",
                                    call_id,
                                )

                        llm._web_search_fallback = True
                        spoken = str(tool_result.get("spoken") or "").strip()
                        if spoken and not tool_result.get("fallback"):
                            await finish_web_voice(
                                format_web_delivery(kind, spoken),
                                reason="spoken_partial",
                            )
                            return

                        kb_line = ""
                        try:
                            kb_line = await asyncio.wait_for(
                                llm.generate_natural_reply(
                                    transcript=transcript,
                                    user_text=user_text,
                                    overlay=(
                                        "Responde en 2-4 frases con lo que sabes sobre la consulta. "
                                        "PROHIBIDO prometer buscar en internet ni invocar herramientas."
                                    ),
                                    path="web_search_kb_fallback",
                                    max_tokens=320,
                                    timeout_sec=12.0,
                                ),
                                timeout=12.0,
                            ) or ""
                        except Exception:
                            logger.warning(
                                "[RETELL-GEMINI] web kb fallback failed call=%s",
                                call_id,
                            )

                        if kb_line.strip():
                            await finish_web_voice(
                                "Señor, no pude obtener información actual en este momento. "
                                f"Basándome en lo que tengo registrado: {kb_line.strip()}",
                                reason="kb_fallback",
                            )
                        else:
                            await finish_web_voice(WEB_SEARCH_VOICE_FALLBACK, reason="empty")
                    except Exception:
                        logger.exception("[RETELL-GEMINI] web fast-path failed call=%s", call_id)
                        await finish_web_voice(WEB_SEARCH_VOICE_FALLBACK, reason="outer_error")

                query_norm = " ".join(str(web_req.get("query") or "").lower().split())
                now = time.time()
                skip_fast_web = False
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
                        "[RETELL-WEB] skip duplicate web fast-path call=%s query=%s",
                        call_id,
                        query_norm[:60],
                    )
                    skip_fast_web = True

                if skip_fast_web:
                    if await deliver_voice(WEB_SEARCH_VOICE_FALLBACK):
                        return
                    await anti_silence_if_unanswered(reason="web_duplicate")
                    return

                clear_pending_advanced_topic(call_id)
                kind = str(web_req.get("kind") or "general")
                async with response_lock:
                    if not _turn_stale():
                        partial_sent = await send_voice_partial(
                            response_id=scheduled_rid,
                            content=web_search_hold_phrase(kind),
                            content_complete=False,
                            generation=my_generation,
                        )
                await handle_web_search_voice(web_req=web_req, query_norm=query_norm)
                return
            elif web_req and not uid:
                logger.warning("[RETELL-GEMINI] web intent without uid call=%s", call_id)
                if await deliver_voice(WEB_SEARCH_VOICE_FALLBACK):
                    return

            # Path conversacional para saludos y charla corta post-saludo.
            if conversational_turn:
                skip_conversational = False
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
                        skip_conversational = True
                    elif scheduled_key and scheduled_key == last_answered_user_key:
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=answered_key gpt_calls=0 call=%s",
                            scheduled_rid,
                            call_id,
                        )
                        skip_conversational = True
                    elif turn_draft_in_progress and scheduled_key == turn_draft_user_key:
                        latest_for_key = turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid)
                        if scheduled_rid < latest_for_key:
                            logger.info(
                                "[RETELL-TURN] rid=%s superseded=draft_busy gpt_calls=0 call=%s",
                                scheduled_rid,
                                call_id,
                            )
                            skip_conversational = True
                    else:
                        turn_draft_in_progress = True
                        turn_draft_user_key = scheduled_key
                if skip_conversational:
                    await ack_superseded_turn(reason="conversational_superseded")
                    return
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
                    if await deliver_voice(reply):
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=%s gpt_calls=%s call=%s path=conversational",
                            scheduled_rid,
                            turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid),
                            gpt_calls,
                            call_id,
                        )
                        logger.info("[RETELL-GEMINI] conversational call=%s: %s", call_id, reply[:80])
                        return
                    await anti_silence_if_unanswered(reason="conversational_deliver_failed")
                    return
                logger.warning(
                    "[RETELL-GEMINI] conversational miss — fallthrough draft_response call=%s",
                    call_id,
                )

            camera_tool = resolve_camera_voice_request(user_text)
            if camera_tool and uid:
                clear_pending_advanced_topic(call_id)
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

            request = ResponseRequiredRequest(
                interaction_type=interaction,  # type: ignore[arg-type]
                response_id=scheduled_rid,
                transcript=transcript,
            )

            skip_draft = False
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
                    skip_draft = True
                elif scheduled_key and scheduled_key == last_answered_user_key and not pending_web:
                    logger.info(
                        "[RETELL-TURN] rid=%s superseded=answered_key gpt_calls=0 call=%s",
                        scheduled_rid,
                        call_id,
                    )
                    skip_draft = True
                elif turn_draft_in_progress and scheduled_key == turn_draft_user_key:
                    latest_for_key = turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid)
                    if scheduled_rid < latest_for_key:
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=draft_busy gpt_calls=0 call=%s",
                            scheduled_rid,
                            call_id,
                        )
                        skip_draft = True
                else:
                    turn_draft_in_progress = True
                    turn_draft_user_key = scheduled_key

            if skip_draft:
                await ack_superseded_turn(reason="draft_superseded_prelock")
                return

            try:
                gpt_calls += 1
                superseded_now, latest_now = _is_superseded_turn_rid(
                    scheduled_rid,
                    scheduled_key,
                    turn_latest_rid,
                )
                if superseded_now:
                    await ack_superseded_turn(reason="draft_superseded")
                    return

                try:
                    final_event = None
                    async for event in llm.draft_response(request):
                        stale, _ = _is_superseded_turn_rid(
                            scheduled_rid,
                            scheduled_key,
                            turn_latest_rid,
                        )
                        if stale:
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
                        if pending_web and (
                            not content
                            or content == FALLBACK_REPLY
                            or is_unwanted_voice_reply(content, user_text=user_text)
                        ):
                            content = WEB_SEARCH_VOICE_FALLBACK
                        if is_unwanted_voice_reply(content, user_text=user_text):
                            logger.warning(
                                "[RETELL-GEMINI] bloqueado relleno chatbot call=%s text=%s reply=%s",
                                call_id,
                                user_text[:60],
                                content[:80],
                            )
                            if _is_concept_question(user_text):
                                regen = await llm.generate_natural_reply(
                                    transcript=transcript,
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
                        await deliver_voice(content)
                    elif not superseded_now:
                        logger.warning(
                            "[RETELL-GEMINI] empty draft_response call=%s rid=%s text=%s",
                            call_id,
                            scheduled_rid,
                            user_text[:80],
                        )
                        await deliver_voice(
                            WEB_SEARCH_VOICE_FALLBACK if pending_web else FALLBACK_REPLY
                        )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "[RETELL-GEMINI] draft_response error call=%s last=%s",
                        call_id,
                        user_text[:80],
                    )
                    await deliver_voice(
                        WEB_SEARCH_VOICE_FALLBACK if pending_web else FALLBACK_REPLY
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

            if partial_sent:
                await complete_partial_or_deliver(
                    WEB_SEARCH_VOICE_FALLBACK if pending_web else FALLBACK_REPLY
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