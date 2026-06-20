"""Retell Custom LLM WebSocket — Gemini 2.5 Pro como cerebro de voz."""

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
)
from app.services.gemini_voice_llm import GeminiVoiceLlm
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
    resolve_instagram_caption_request,
    resolve_meta_publish_request,
    resolve_web_search_request,
    is_inaudible_or_noise,
    should_clear_pending_script,
    should_execute_advanced_now,
    should_respond_to_transcript,
    is_unwanted_voice_reply,
    transcript_has_meta_publish_context,
    _is_concept_question,
    web_search_error_phrase,
)
from app.services.voice_tool_executor import execute_voice_tool
from app.services.voice_spoken import split_voice_delivery_chunks
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
FALLBACK_REPLY = "Disculpe, señor. Tuve un inconveniente. ¿Puede repetir?"


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
    generation_seq = 0
    answered_response_ids: set[int] = set()
    greeting_release_task: asyncio.Task[None] | None = None
    message_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    user_id = resolve_call_user(call_id)
    if user_id:
        llm.set_user_id(user_id)
        logger.info("[RETELL-GEMINI] user_id=%s call=%s (registry)", user_id[:8], call_id)

    from app.build_info import BUILD_VERSION
    from app.domain.openai_voice_prompt import voice_prompt_diagnostics

    prompt_diag = voice_prompt_diagnostics()
    logger.info(
        "[RETELL-GEMINI] session prompt call=%s build=%s sha=%s chars=%s seth=%s",
        call_id,
        BUILD_VERSION,
        prompt_diag.get("prompt_sha256_prefix"),
        prompt_diag.get("prompt_chars"),
        prompt_diag.get("includes_seth"),
    )

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
        begin_text = await llm.draft_greeting()
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
        logger.info("[RETELL-GEMINI] saludo enviado call=%s reason=%s", call_id, reason)

    await send_greeting(0, reason="immediate")

    async def send_voice_partial(
        *,
        response_id: int,
        content: str,
        content_complete: bool,
        generation: int | None = None,
    ) -> bool:
        if generation is not None and generation != generation_seq:
            return False
        payload = {
            "response_type": "response",
            "response_id": response_id,
            "content": content,
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
        if generation is not None and generation != generation_seq:
            logger.info(
                "[RETELL-GEMINI] skip stale generation send rid=%s call=%s",
                response_id,
                call_id,
            )
            return False
        if response_id in answered_response_ids:
            logger.info(
                "[RETELL-GEMINI] skip duplicate send rid=%s call=%s",
                response_id,
                call_id,
            )
            return False
        if response_id < active_response_id:
            return False
        chunks = split_voice_delivery_chunks(content)
        for chunk, complete in chunks:
            if response_id < active_response_id:
                return False
            payload = {
                "response_type": "response",
                "response_id": response_id,
                "content": chunk,
                "content_complete": complete,
                "end_call": False,
            }
            await websocket.send_json(payload)
        active_response_id = response_id
        answered_response_ids.add(response_id)
        if user_key:
            last_answered_user_key = user_key
        logger.info(
            "[RETELL-GEMINI] respuesta enviada call=%s rid=%s chars=%s chunks=%s",
            call_id,
            response_id,
            len(content),
            len(chunks),
        )
        return True

    async def handle_message(request_json: dict) -> None:
        nonlocal active_response_id, debounce_task, last_scheduled_user_key, generation_seq

        interaction = str(request_json.get("interaction_type") or "")
        note_ws_interaction(call_id, interaction)
        logger.info("[RETELL-GEMINI] interaction=%s call=%s", interaction, call_id)

        response_id = int(request_json.get("response_id") or 0)
        if response_id in answered_response_ids:
            logger.info(
                "[RETELL-GEMINI] skip answered rid=%s call=%s",
                response_id,
                call_id,
            )
            return

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
            logger.info("[RETELL-GEMINI] call_details call=%s (saludo ya enviado)", call_id)
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

        active_response_id = max(active_response_id, response_id)

        generation_seq += 1
        my_generation = generation_seq

        if debounce_task and not debounce_task.done():
            debounce_task.cancel()

        last_scheduled_user_key = user_key
        wait_s = _debounce_wait_s(user_text)

        async def run_debounced() -> None:
            nonlocal active_response_id, last_answered_user_key
            scheduled_key = user_key
            scheduled_rid = response_id
            try:
                await post_greeting_ready.wait()
                await asyncio.sleep(wait_s)
            except asyncio.CancelledError:
                return

            if my_generation != generation_seq:
                logger.info(
                    "[RETELL-GEMINI] skip superseded generation call=%s seq=%s current=%s",
                    call_id,
                    my_generation,
                    generation_seq,
                )
                return

            if scheduled_key != last_scheduled_user_key:
                logger.info("[RETELL-GEMINI] skip superseded debounce call=%s", call_id)
                return

            if scheduled_rid in answered_response_ids:
                logger.info(
                    "[RETELL-GEMINI] skip answered debounced rid=%s call=%s",
                    scheduled_rid,
                    call_id,
                )
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
            if uid:
                from app.services import voice_client_session as vcs

                if vcs.is_awaiting_instagram_caption(uid) and not is_script_demo_request(user_text):
                    advanced_req = None
            if not advanced_req and (
                has_advanced_confirmation(user_text)
                or is_explicit_advanced_activation(user_text)
            ) and not is_script_delivered(call_id):
                advanced_req = fallback_advanced_topic(transcript, pending_topic=pending_now)

            conversational_turn = (
                not advanced_req
                and not resolve_meta_publish_request(user_text)
                and not resolve_instagram_caption_request(user_text, transcript, user_id=uid)
                and (
                    is_casual_conversation(user_text)
                    or (
                        is_small_talk(user_text, transcript)
                        and not resolve_web_search_request(user_text, transcript)
                    )
                )
            )
            if conversational_turn:
                conv_request = ResponseRequiredRequest(
                    interaction_type=interaction,
                    response_id=response_id,
                    transcript=transcript,
                )
                reply = await llm.draft_conversational_response(conv_request)
                if reply:
                    async with response_lock:
                        await send_voice_response(
                            response_id=response_id,
                            content=reply,
                            user_key=user_key,
                            generation=my_generation,
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
                    if response_id < active_response_id:
                        return
                    if is_vision:
                        await send_voice_partial(
                            response_id=response_id,
                            content="Un momento, señor. Analizo con visión.",
                            content_complete=False,
                            generation=my_generation,
                        )
                    tool_args: dict = {}
                    if is_vision:
                        tool_args["pregunta"] = user_text
                    try:
                        tool_result = await asyncio.wait_for(
                            execute_voice_tool(camera_tool, uid, tool_args),
                            timeout=40.0 if is_vision else 12.0,
                        )
                    except asyncio.TimeoutError:
                        tool_result = {
                            "spoken": "No pude completar el análisis visual, señor.",
                        }
                    spoken = str(tool_result.get("spoken") or "").strip()
                    if is_vision:
                        await send_voice_partial(
                            response_id=response_id,
                            content=spoken or "No pude analizar la imagen, señor.",
                            content_complete=True,
                            generation=my_generation,
                        )
                        active_response_id = response_id
                        answered_response_ids.add(response_id)
                        if user_key:
                            last_answered_user_key = user_key
                    else:
                        await send_voice_response(
                            response_id=response_id,
                            content=spoken or "Completado, señor.",
                            user_key=user_key,
                        )
                logger.info("[RETELL-GEMINI] camera call=%s tool=%s", call_id, camera_tool)
                return

            meta_req = resolve_meta_publish_request(user_text)
            if not meta_req:
                meta_req = resolve_instagram_caption_request(
                    user_text,
                    transcript,
                    user_id=uid,
                )
            if meta_req and uid:
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
                    if response_id < active_response_id:
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
                        response_id=response_id,
                        content=spoken,
                        user_key=user_key,
                        generation=my_generation,
                    )
                logger.info(
                    "[RETELL-GEMINI] meta_publish call=%s tool=%s caption=%s",
                    call_id,
                    tool_name,
                    (meta_req.get("caption") or "")[:80],
                )
                return

            web_req = resolve_web_search_request(user_text, transcript)
            if web_req and uid:
                clear_pending_advanced_topic(call_id)
                llm._pending_advanced = None
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
                    chunks = split_voice_delivery_chunks(full)
                    for chunk, complete in chunks:
                        if response_id < active_response_id:
                            return
                        await send_voice_partial(
                            response_id=response_id,
                            content=chunk,
                            content_complete=complete,
                            generation=my_generation,
                        )
                    active_response_id = response_id
                    answered_response_ids.add(response_id)
                    if user_key:
                        last_answered_user_key = user_key
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
                        generation=my_generation,
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
                        chunks = [
                            (
                                spoken
                                or "Disculpe, señor. No pude completar el análisis avanzado.",
                                True,
                            )
                        ]
                    else:
                        chunks = split_voice_delivery_chunks(spoken)
                    for chunk, complete in chunks:
                        if response_id < active_response_id:
                            return
                        await send_voice_partial(
                            response_id=response_id,
                            content=chunk,
                            content_complete=complete,
                            generation=my_generation,
                        )
                    active_response_id = response_id
                    answered_response_ids.add(response_id)
                    if user_key:
                        last_answered_user_key = user_key
                    clear_pending_advanced_topic(call_id)
                    llm._pending_advanced = None
                    mark_script_delivered(call_id)
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
            ) and uid and not is_camera_voice_command(user_text) and not is_script_delivered(call_id):
                if not (
                    transcript_has_meta_publish_context(transcript)
                    or is_meta_publish_intent(user_text)
                ):
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
                                generation=my_generation,
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
                            if not spoken:
                                chunks = [("Disculpe, señor. No pude completar el análisis.", True)]
                            else:
                                chunks = split_voice_delivery_chunks(spoken)
                            for chunk, complete in chunks:
                                await send_voice_partial(
                                    response_id=response_id,
                                    content=chunk,
                                    content_complete=complete,
                                    generation=my_generation,
                                )
                            active_response_id = response_id
                            answered_response_ids.add(response_id)
                            if user_key:
                                last_answered_user_key = user_key
                            clear_pending_advanced_topic(call_id)
                            llm._pending_advanced = None
                            mark_script_delivered(call_id)
                        return
                else:
                    logger.info("[RETELL-GEMINI] skip advanced confirm — meta publish context")

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
                        generation=my_generation,
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