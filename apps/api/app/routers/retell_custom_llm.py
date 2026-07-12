"""Retell Custom LLM WebSocket — Gemini 2.5 Flash como cerebro conversacional de voz."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.cognitive_intents import (
    is_camera_voice_command,
    is_camera_activation_intent,
    is_camera_deactivation_intent,
    is_meta_publish_intent,
    is_script_demo_request,
    is_web_research_intent,
)
from app.services.voice_llm_factory import build_voice_llm
from app.services.retell_call_registry import (
    bind_call_user,
    release_call_user,
    resolve_call_user,
)
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
from app.services.ced_orchestrator import (
    detect_strict_intent_v2,
    detect_voice_module_intent,
    get_context_overlay,
    get_orchestrator,
)
from app.services.voice_tool_executor import (
    NAVIGATION_TIMEOUT_SEC,
    SEARCH_WEB_TIMEOUT_SEC,
    execute_voice_tool,
)
from app.services.voice_tool_async import execute_deferred_tool_batch
from app.services.voice_spoken import (
    chunk_ends_with_punctuation,
    compose_voice_tool_delivery,
    finalize_voice_delivery_text,
    format_vision_response,
    split_voice_delivery_chunks,
    voice_delivery_chunks,
)
from app.services.voice_response_guard import guard_voice_response
from app.services.voice_latency import get_turn, start_turn
from app.services.voice_intent_gate import has_explicit_module_signal, should_run_orchestrator
from app.services.voice_casual import is_casual_voice_turn
from app.services.voice_filler_bank import FILLER_MIN_HOLD_S, pick_voice_filler
from app.services.voice_test_mode import is_gemini_standalone_voice_test
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
GREETING_COMPLETE_FALLBACK = "CED en línea, señor. Estoy listo para asistirle."
WEB_SEARCH_FAST_PATH_TIMEOUT_SEC = 15.0
GPS_INSTRUCTION_CHANNEL = "navigation_instruction"

_turn_filler_sent: dict[str, bool] = {}
_turn_handled: dict[str, bool] = {}
_api_uid_lookups: set[str] = set()


async def resolve_call_user_robust(
    call_id: str, payload: dict[str, Any] | None = None
) -> str | None:
    """Resuelve user_id con fallback a la API de Retell.

    El registro call_id→user_id vive en memoria y se pierde si la API reinicia
    (redeploy). Sin esto, las tools de voz fallan con "no identifiqué al usuario".
    Ante un fallo del registro, recupera el user_id desde la metadata de la
    llamada vía la API de Retell y lo re-vincula. Se intenta una sola vez por
    llamada para no añadir latencia repetida.
    """
    uid = resolve_call_user(call_id, payload)
    if uid:
        return uid
    cid = (call_id or "").strip()
    if not cid or cid in _api_uid_lookups:
        return None
    _api_uid_lookups.add(cid)
    try:
        from app.services.retell_client import get_retell_client

        client = get_retell_client()
        if not client:
            return None
        detail = await asyncio.to_thread(client.call.retrieve, call_id=cid)
        meta = getattr(detail, "metadata", None) or {}
        val = str(meta.get("user_id") or meta.get("userId") or "").strip()
        if val:
            bind_call_user(cid, val)
            logger.info("[RETELL-GEMINI] user_id recuperado vía API call=%s", cid)
            return val
    except Exception as exc:  # noqa: BLE001 — fallback best-effort
        logger.warning("[RETELL-GEMINI] fallback user_id vía API falló call=%s: %s", cid, exc)
    return None


def _voice_turn_key(call_id: str, rid: int) -> str:
    return f"{call_id}:{rid}"


def mark_turn_handled(call_id: str, rid: int) -> None:
    _turn_handled[_voice_turn_key(call_id, rid)] = True


def turn_already_handled(call_id: str, rid: int) -> bool:
    return _turn_handled.get(_voice_turn_key(call_id, rid), False)


def reset_turn_filler_state(call_id: str, rid: int) -> None:
    _turn_filler_sent.pop(_voice_turn_key(call_id, rid), None)


def try_mark_turn_filler_sent(call_id: str, rid: int) -> bool:
    key = _voice_turn_key(call_id, rid)
    if _turn_filler_sent.get(key):
        return False
    _turn_filler_sent[key] = True
    return True


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
    if words <= 5:
        return 0.06
    if words >= 20:
        return 0.20
    if words >= 10:
        return 0.14
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

    llm = build_voice_llm()
    if is_gemini_standalone_voice_test():
        logger.warning(
            "[VOICE-TEST-GEMINI] *** STANDALONE MODE — Gemini directo, sin orquestador/tools *** call=%s",
            call_id,
        )
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

    user_id = await resolve_call_user_robust(call_id)
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

    async def send_direct_retell_audio(text: str) -> None:
        """Canal GPS — audio directo a Retell sin pasar por Gemini."""
        msg = (text or "").strip()
        if not msg:
            return
        await websocket.send_json(
            {
                "response_type": "agent_interrupt",
                "content": msg,
                "interrupt_prior_spoke_content": False,
            }
        )

    async def handle_navigation_instruction_audio(uid: str, *, call: str) -> bool:
        """Bypass total del LLM para instrucciones GPS habladas."""
        from app.services.navigation_voice import pop_navigation_speech

        nav_text = pop_navigation_speech(uid)
        if not nav_text:
            return False
        await send_direct_retell_audio(nav_text)
        logger.info(
            "[RETELL-GEMINI] navigation %s call=%s text=%s",
            GPS_INSTRUCTION_CHANNEL,
            call,
            nav_text[:80],
        )
        return True

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
            begin_text = (await llm.draft_greeting() or "").strip()
            if (
                len(begin_text) < 20
                or not chunk_ends_with_punctuation(begin_text)
                or begin_text.lower() in {"ced en", "ced"}
            ):
                begin_text = GREETING_COMPLETE_FALLBACK
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
        skip_prefix: str = "",
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
        from app.services.stream_delta import strip_prefix_overlap

        body = strip_prefix_overlap(skip_prefix, content) if skip_prefix else content
        if not (body or "").strip():
            if skip_prefix:
                await send_voice_partial(
                    response_id=response_id,
                    content="",
                    content_complete=True,
                    generation=generation,
                )
                answered_response_ids.add(response_id)
                return True
            body = content
        if response_id in answered_response_ids:
            logger.info(
                "[RETELL-OPENAI] skip duplicate send rid=%s call=%s",
                response_id,
                call_id,
            )
            return False
        safe, blocked = guard_voice_response(body)
        if blocked:
            logger.warning(
                "[RETELL-OPENAI] blocked outbound code leak rid=%s call=%s preview=%s",
                response_id,
                call_id,
                body[:80],
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
        # Retell: deltas incrementales; un solo envío si cabe en un mensaje.
        chunks = [(content, True)]
        if len(content) > 8000:
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

        uid = await resolve_call_user_robust(call_id, request_json)
        if uid:
            llm.set_user_id(uid)
            from app.services import voice_client_session as vcs

            vcs.sync_voice_call(uid, call_id)

        if interaction == "ping_pong":
            uid = resolve_call_user(call_id, request_json)
            if uid:
                await handle_navigation_instruction_audio(uid, call=call_id)
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
        if not is_gemini_standalone_voice_test():
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
        pending_web = None if is_gemini_standalone_voice_test() else resolve_web_search_request(user_text, transcript)
        strict_module_early = None
        if not is_gemini_standalone_voice_test():
            # Un ancla estricta de módulo (ej. "resumen de mis finanzas", "hazme un pdf")
            # SIEMPRE gana al fast-path de búsqueda web. Sin esto, "dame el resumen de
            # mis finanzas" caía en "consulto las noticias" porque el web fast-path corre
            # antes que el orquestador. web_search sí puede seguir su camino.
            strict_module_early = detect_strict_intent_v2(user_text)
            if not strict_module_early and has_explicit_module_signal(user_text):
                strict_module_early = detect_voice_module_intent(
                    user_text, transcript, user_id=uid or ""
                )
        if pending_web and strict_module_early and strict_module_early != "web_search":
            logger.info(
                "[RETELL-ORCH] ancla estricta %s cancela web fast-path call=%s",
                strict_module_early,
                call_id,
            )
            pending_web = None
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
            deferred_tools_pending = False
            last_partial_content = ""
            filler_sent_at: float | None = None
            filler_hold_done = False

            def _turn_rid_stale(rid: int = scheduled_rid) -> bool:
                stale, _ = _is_superseded_turn_rid(rid, scheduled_key, turn_latest_rid)
                return stale

            def _turn_stale(rid: int = scheduled_rid) -> bool:
                return _turn_rid_stale(rid) or my_generation != generation_seq

            reset_turn_filler_state(call_id, scheduled_rid)

            async def send_filler_once_partial(text: str) -> bool:
                nonlocal partial_sent, last_partial_content
                if not try_mark_turn_filler_sent(call_id, scheduled_rid):
                    return False
                if _turn_stale():
                    return False
                async with response_lock:
                    sent = await send_voice_partial(
                        response_id=scheduled_rid,
                        content=text.strip(),
                        content_complete=False,
                        generation=my_generation,
                    )
                if sent:
                    last_partial_content = text.strip()
                    partial_sent = True
                return sent

            async def fire_latency_filler(
                category: str,
                *,
                module: str | None = None,
            ) -> None:
                nonlocal filler_sent_at
                phrase = pick_voice_filler(
                    category,
                    call_id=call_id,
                    module=module,
                )
                if await send_filler_once_partial(phrase):
                    filler_sent_at = time.monotonic()
                    logger.info(
                        "[RETELL-FILLER] sent category=%s module=%s call=%s rid=%s",
                        category,
                        module or "-",
                        call_id[:12],
                        scheduled_rid,
                    )

            async def ensure_filler_hold() -> None:
                nonlocal filler_hold_done
                if filler_hold_done or not partial_sent or filler_sent_at is None:
                    return
                elapsed = time.monotonic() - filler_sent_at
                wait_s = FILLER_MIN_HOLD_S - elapsed
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
                filler_hold_done = True

            def _can_deliver_turn(rid: int = scheduled_rid) -> bool:
                if rid in answered_response_ids:
                    return False
                latest = turn_latest_rid.get(_turn_slot(scheduled_key), rid)
                return rid >= latest

            async def deliver_voice(
                content: str,
                *,
                rid: int = scheduled_rid,
                generation: int | None = None,
            ) -> bool:
                nonlocal partial_sent, last_partial_content
                if not _can_deliver_turn(rid):
                    return False
                await ensure_filler_hold()
                async with response_lock:
                    delivered = await send_voice_response(
                        response_id=rid,
                        content=content,
                        user_key=scheduled_key,
                        generation=generation,
                        skip_prefix=last_partial_content if partial_sent else "",
                    )
                if delivered:
                    partial_sent = False
                    last_partial_content = ""
                return delivered

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
                fallback_content = (
                    "Disculpe señor, ¿en qué le puedo ayudar?"
                    if not pending_web
                    else WEB_SEARCH_VOICE_FALLBACK
                )
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
                if uid:
                    orch = get_orchestrator(call_id)
                    if orch.active_module:
                        await orch.deactivate_current(user_id=uid)
                await deliver_voice(fallback_content)

            async def ack_superseded_turn(*, reason: str) -> None:
                """Turno reemplazado por uno más nuevo — no hablar fallback."""
                if scheduled_rid in answered_response_ids:
                    return
                await ack_empty_response(response_id=scheduled_rid, reason=reason)

            async def complete_partial_or_deliver(content: str) -> bool:
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

            if is_gemini_standalone_voice_test():
                skip_standalone = False
                async with response_lock:
                    superseded, latest_rid = _is_superseded_turn_rid(
                        scheduled_rid,
                        scheduled_key,
                        turn_latest_rid,
                    )
                    if superseded:
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=%s gpt_calls=0 call=%s path=standalone",
                            scheduled_rid,
                            latest_rid,
                            call_id,
                        )
                        skip_standalone = True
                    elif scheduled_key and scheduled_key == last_answered_user_key:
                        logger.info(
                            "[RETELL-TURN] rid=%s superseded=answered_key gpt_calls=0 call=%s path=standalone",
                            scheduled_rid,
                            call_id,
                        )
                        skip_standalone = True
                    elif turn_draft_in_progress and scheduled_key == turn_draft_user_key:
                        latest_for_key = turn_latest_rid.get(
                            _turn_slot(scheduled_key),
                            scheduled_rid,
                        )
                        if scheduled_rid < latest_for_key:
                            logger.info(
                                "[RETELL-TURN] rid=%s superseded=draft_busy gpt_calls=0 call=%s path=standalone",
                                scheduled_rid,
                                call_id,
                            )
                            skip_standalone = True
                    else:
                        turn_draft_in_progress = True
                        turn_draft_user_key = scheduled_key
                if skip_standalone:
                    await ack_superseded_turn(reason="standalone_superseded")
                    return
                conv_request = ResponseRequiredRequest(
                    interaction_type="response_required",
                    response_id=scheduled_rid,
                    transcript=transcript,
                )
                llm.set_latency_context(call_id, scheduled_rid)
                try:
                    reply = await llm.draft_conversational_response(conv_request)
                finally:
                    turn_draft_in_progress = False
                    turn_draft_user_key = ""
                if _turn_rid_stale() or my_generation != generation_seq:
                    await ack_superseded_turn(reason="standalone_stale_after_llm")
                    return
                if reply and await deliver_voice(reply, generation=my_generation):
                    logger.info(
                        "[VOICE-TEST-GEMINI] delivered rid=%s call=%s chars=%s",
                        scheduled_rid,
                        call_id,
                        len(reply),
                    )
                    return
                await anti_silence_if_unanswered(reason="standalone_gemini_empty")
                return

            from app.services.system_clock import try_instant_datetime_reply

            conversational_turn = is_casual_voice_turn(user_text, transcript)

            clock_reply = try_instant_datetime_reply(
                user_text,
                transcript=transcript,
                for_voice=True,
            )
            if clock_reply:
                if await deliver_voice(clock_reply):
                    logger.info(
                        "[RETELL-GEMINI] instant datetime call=%s: %s",
                        call_id,
                        clock_reply[:80],
                    )
                    return
                await anti_silence_if_unanswered(reason="datetime_deliver_failed")
                return

            # Charla casual — antes del orquestador: KB interno o Llama, sin tools ni filler.
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
                if not reply:
                    from app.services.voice_casual import try_casual_empathy_fallback

                    reply = try_casual_empathy_fallback(user_text)
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
                if await deliver_voice(FALLBACK_REPLY):
                    return
                await anti_silence_if_unanswered(reason="conversational_miss")
                return

            from app.services.voice_intent_gate import detect_local_module_hints

            module_hints = detect_local_module_hints(user_text)
            if "advanced" in module_hints and uid and not get_orchestrator(call_id).active_module:
                set_pending_advanced_topic(call_id, user_text)
                advanced_reply = (
                    "Señor, el modo avanzado con Claude funciona en el chat de texto. "
                    "Abra el panel Avanzado para continuar su consulta con análisis profundo."
                )
                if await deliver_voice(advanced_reply):
                    logger.info(
                        "[RETELL-ORCH] advanced mode delegated to text call=%s",
                        call_id,
                    )
                    return
                await anti_silence_if_unanswered(reason="advanced_delegate_failed")
                return

            if pending_web and uid and not conversational_turn:
                kind = str(pending_web.get("kind") or "general")
                query = str(pending_web.get("query") or user_text).strip()
                if query:
                    await fire_latency_filler("web_search")
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(
                                "search_web",
                                uid,
                                {"query": query, "kind": kind},
                            ),
                            timeout=SEARCH_WEB_TIMEOUT_SEC + 2.0,
                        )
                        spoken = str(tool_result.get("spoken") or "").strip()
                        if tool_result.get("status") == "success" and spoken:
                            web_content = format_web_delivery(kind, spoken)
                        else:
                            web_content = WEB_SEARCH_VOICE_FALLBACK
                    except asyncio.TimeoutError:
                        logger.warning(
                            "[RETELL-GEMINI] fast-path search_web timeout call=%s query=%s",
                            call_id,
                            query[:80],
                        )
                        web_content = WEB_SEARCH_VOICE_FALLBACK
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "[RETELL-GEMINI] fast-path search_web failed call=%s",
                            call_id,
                        )
                        web_content = WEB_SEARCH_VOICE_FALLBACK
                    if await deliver_voice(web_content):
                        logger.info(
                            "[RETELL-GEMINI] fast-path web search call=%s kind=%s",
                            call_id,
                            kind,
                        )
                        return
                    await anti_silence_if_unanswered(reason="web_fast_path_failed")
                    return

            if uid and is_camera_deactivation_intent(user_text):
                if not turn_already_handled(call_id, scheduled_rid):
                    mark_turn_handled(call_id, scheduled_rid)
                    orch = get_orchestrator(call_id)
                    await execute_voice_tool("request_camera_deactivation", uid, {})
                    if orch.active_module:
                        await orch.deactivate_current(user_id=uid)
                    delivered = await complete_partial_or_deliver(
                        "Cámara desactivada, señor."
                    )
                    if not delivered:
                        await anti_silence_if_unanswered(
                            reason="camera_deactivate_deliver_failed"
                        )
                    return

            orch = get_orchestrator(call_id)
            orch_result = None
            forced_module = detect_strict_intent_v2(user_text)
            run_orchestrator = should_run_orchestrator(
                user_text,
                active_module=orch.active_module,
                forced_module=forced_module,
            )
            if run_orchestrator and not forced_module and has_explicit_module_signal(user_text):
                forced_module = detect_voice_module_intent(
                    user_text, transcript, user_id=uid or ""
                )
            if forced_module:
                logger.info(
                    "[RETELL-ORCH] forced module=%s call=%s text=%s",
                    forced_module,
                    call_id,
                    user_text[:60],
                )
            if uid and run_orchestrator:
                mod_hint = forced_module or orch.active_module
                if mod_hint:
                    await fire_latency_filler("module", module=mod_hint)
                clear_pending_advanced_topic(call_id)
                orch_result = await orch.process(
                    user_text=user_text,
                    transcript=transcript,
                    call_id=call_id,
                    user_id=uid,
                )
                llm.set_module_overlay(orch_result.context_overlay or "")
                if orch_result.handles_response:
                    if orch_result.send_filler:
                        async with response_lock:
                            if not _turn_stale():
                                await fire_latency_filler(
                                    "module",
                                    module=orch.active_module or forced_module,
                                )
                    if turn_already_handled(call_id, scheduled_rid) and orch.active_module == "camera":
                        await ack_empty_response(
                            response_id=scheduled_rid,
                            reason="orch_camera_handled",
                        )
                        return
                    if _turn_rid_stale():
                        await ack_superseded_turn(reason="orch_stale")
                        return
                    spoken = (orch_result.spoken or "").strip()
                    if spoken:
                        if orch.active_module in ("camera", "publish"):
                            mark_turn_handled(call_id, scheduled_rid)
                        delivered = await complete_partial_or_deliver(spoken)
                        if not delivered:
                            await anti_silence_if_unanswered(reason="orch_deliver_failed")
                        logger.info(
                            "[RETELL-ORCH] module=%s call=%s delivered=%s",
                            orch.active_module,
                            call_id,
                            delivered,
                        )
                    else:
                        await anti_silence_if_unanswered(reason="orch_empty_spoken")
                    return
            elif uid:
                llm.set_module_overlay(
                    get_context_overlay(get_orchestrator(call_id).active_module) or ""
                )

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

            if turn_already_handled(call_id, scheduled_rid):
                await ack_empty_response(
                    response_id=scheduled_rid,
                    reason="turn_already_handled",
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
                    draft_events: list[Any] = []
                    voice_streamed = False
                    streamed_text = ""
                    await fire_latency_filler("general")
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
                        draft_events.append(event)
                        piece = (event.content or "").strip()
                        if piece:
                            await ensure_filler_hold()
                            async with response_lock:
                                if _turn_stale():
                                    break
                                sent = await send_voice_partial(
                                    response_id=scheduled_rid,
                                    content=piece,
                                    content_complete=False,
                                    generation=my_generation,
                                )
                            if sent:
                                voice_streamed = True
                                streamed_text += piece
                        if event.content_complete:
                            async with response_lock:
                                if not _turn_stale():
                                    await send_voice_partial(
                                        response_id=scheduled_rid,
                                        content="",
                                        content_complete=True,
                                        generation=my_generation,
                                    )
                            voice_streamed = True
                            answered_response_ids.add(scheduled_rid)
                            if scheduled_key:
                                last_answered_user_key = scheduled_key
                            break

                    deferred_batch = llm.take_deferred_batch()
                    if deferred_batch is not None and draft_events:
                        mark_turn_handled(call_id, scheduled_rid)

                        async def deliver_tool_spoken(text: str) -> bool:
                            if _turn_stale():
                                return False
                            body = text
                            if any(
                                c.name in ("analyze_camera_frame", "buscar_lo_visible")
                                for c in deferred_batch.calls
                            ):
                                body = format_vision_response(text) or text
                            delivery = finalize_voice_delivery_text(body)
                            return await deliver_voice(delivery)

                        async def run_deferred_tools() -> None:
                            try:
                                results = await execute_deferred_tool_batch(
                                    deferred_batch,
                                    user_id=uid,
                                    deliver=deliver_tool_spoken,
                                    is_stale=_turn_stale,
                                    build_tool_payload=llm.build_async_tool_payload,
                                )
                                if results and not _turn_stale():
                                    await llm.apply_deferred_results(
                                        deferred_batch,
                                        results=results,
                                    )
                            except Exception:
                                logger.exception(
                                    "[RETELL-GEMINI] deferred tools failed call=%s rid=%s",
                                    call_id,
                                    scheduled_rid,
                                )
                                if not _turn_stale():
                                    await deliver_voice(
                                        "Disculpe señor, hubo un inconveniente."
                                    )

                        asyncio.create_task(run_deferred_tools())
                        deferred_tools_pending = True
                        logger.info(
                            "[RETELL-GEMINI] deferred tools scheduled call=%s rid=%s count=%s",
                            call_id,
                            scheduled_rid,
                            len(deferred_batch.calls),
                        )
                        return

                    if voice_streamed and streamed_text.strip():
                        last_delivered_voice_content = normalize_voice_delivery_text(
                            streamed_text
                        )
                        logger.info(
                            "[RETELL-DELIVERY] streamed call=%s rid=%s chars=%s",
                            call_id,
                            scheduled_rid,
                            len(streamed_text),
                        )
                        return

                    final_event = draft_events[-1] if draft_events else None
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
                if not deferred_tools_pending:
                    await anti_silence_if_unanswered(reason="draft_finally")
                logger.info(
                    "[RETELL-TURN] rid=%s superseded=%s gpt_calls=%s call=%s path=draft",
                    scheduled_rid,
                    turn_latest_rid.get(_turn_slot(scheduled_key), scheduled_rid),
                    gpt_calls,
                    call_id,
                )

            if partial_sent and scheduled_rid not in answered_response_ids:
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
        _api_uid_lookups.discard((call_id or "").strip())
        logger.info("[RETELL-GEMINI] WebSocket cerrado call_id=%s", call_id)