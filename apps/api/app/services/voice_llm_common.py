"""Utilidades compartidas — capa LLM de voz Retell (OpenAI GPT-4.1 / legacy Gemini)."""

from __future__ import annotations

import re

from app.domain.ced_strategy_consultant import CED_STRATEGY_CONSULTATION_OVERLAY
from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.services.deliverable_replies import VOICE_DELIVERABLE_OVERLAY, is_deliverable_request, is_strategy_consultation_topic
from app.services.retell_custom_llm import is_generic_agent_line, is_unwanted_voice_reply
from app.services.retell_llm_types import Utterance
from app.services.voice_spoken import (
    PROMPT_DELIVERY_OVERLAY,
    is_advisory_voice_query,
    is_prompt_creation_request,
)

MAX_HISTORY_TURNS = 10
SESSION_MAX_MINUTES = 30.0
FALLBACK_REPLY = "Disculpe, señor. Tuve un inconveniente técnico. ¿Puede repetir?"
VOICE_TIMEOUT_REPLY = "Disculpe señor, tardé demasiado. ¿Puede repetir?"
VOICE_ERROR_REPLY = "Disculpe señor, tuve un inconveniente. ¿Puede repetir?"
WEB_SEARCH_VOICE_FALLBACK = (
    "Señor, no pude obtener información actual en este momento. "
    "Basándome en lo que tengo registrado, le oriento con lo disponible. "
    "¿Desea que lo intente de nuevo?"
)

_BASE_VOICE_PROMPT: str | None = None


def _cached_base_voice_prompt() -> str:
    global _BASE_VOICE_PROMPT
    if _BASE_VOICE_PROMPT is None:
        _BASE_VOICE_PROMPT = build_ced_voice_system_prompt()
    return _BASE_VOICE_PROMPT

CONVERSATIONAL_TURN_OVERLAY = """
# TURNO CONVERSACIONAL — PRIORIDAD ABSOLUTA
El usuario está en charla personal, saludo casual o comparte algo emocional/cotidiano.
NO invoques herramientas. Responde con empatía natural: 1-2 oraciones completas.
PROHIBIDO prometer buscar o investigar.
PROHIBIDO responder solo "¿En qué puedo ayudarle?" o variantes transaccionales.
Valida lo que dice antes de ofrecer ayuda. No fuerces tareas ni prospección.
""".strip()

GREETING_OVERLAY = """
# SALUDO INICIAL DE VOZ — UNA SOLA FRASE CORTA
Acabas de conectar una llamada de voz. El usuario aún no ha hablado.
Di UNA sola frase breve (máximo 8 palabras). Nada más.
Válido: "CED en línea, señor." / "Buenos días, señor."
PROHIBIDO: "Soy CED", "la voz del Castillo", presentaciones largas, preguntas al final.
PROHIBIDO: monólogo, listar capacidades, "¿En qué puedo ayudarle?", "A su servicio", "operativo".
""".strip()

REMINDER_OVERLAY = """
# SILENCIO PROLONGADO
El usuario lleva un momento en silencio. Usa el transcript para contexto.
Responde con UNA frase natural y empática — pregunta si sigue ahí, ofrece paciencia,
o retoma el tema anterior si aplica.
PROHIBIDO: "Sigo atento", "¿Continuamos?", tono de chatbot de soporte.
""".strip()

DELAY_ACK_OVERLAY = """
# DEMORA EN PROCESAR
La generación tardó. Responde con UNA frase breve que reconozca la demora con calidez.
Ejemplo: "Permítame un momento, señor." / "Un segundo, señor, ya le respondo."
NO listes capacidades ni uses "¿En qué puedo ayudarle?"
""".strip()

REFORMULATE_EMPATHY_OVERLAY = """
# REFORMULAR CON MÁS EMPATÍA (VOZ)
Tu respuesta anterior fue demasiado genérica, transaccional o vacía.
Reescribe con empatía genuina — la misma calidez que el chat de texto CED.
Máximo 2-4 oraciones completas para voz. Valida lo que compartió antes de aconsejar.
Si pide consejo, da 2-3 acciones concretas y breves — no un ensayo largo.
PROHIBIDO: markdown, asteriscos, listas numeradas largas, "¿En qué puedo ayudarle?",
"operativo", "a su servicio", relleno de chatbot.
""".strip()


def ensure_voice_reply(text: str | None, *, fallback: str | None = None) -> str:
    """Garantiza texto hablable en cada turno de voz."""
    from app.services.voice_spoken import finalize_voice_delivery_text

    cleaned = finalize_voice_delivery_text(str(text or "").strip())
    if cleaned:
        return cleaned
    return fallback or FALLBACK_REPLY


def voice_generation_limits(user_text: str) -> tuple[int, float]:
    if is_deliverable_request(user_text):
        return 3200, 28.0
    if is_prompt_creation_request(user_text):
        return 2048, 28.0
    if is_advisory_voice_query(user_text):
        return 1536, 22.0
    try:
        from app.services.cognitive_intents import (
            is_news_intent,
            is_personal_vent_intent,
            requires_live_web,
        )

        if is_personal_vent_intent(user_text):
            return 1536, 22.0
        if is_news_intent(user_text) or requires_live_web(user_text):
            return 1536, 22.0
    except Exception:  # noqa: BLE001
        pass
    return 896, 16.0


def delivery_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def prompt_sha_prefix() -> str:
    return str(voice_prompt_diagnostics().get("prompt_sha256_prefix") or "")


def log_voice_delivery(provider: str, path: str, text: str, *, user_text: str = "") -> None:
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        "[RETELL-%s] response_source=%s path=%s prompt_sha=%s user=%s chars=%s preview=%s",
        provider.upper(),
        provider,
        path,
        prompt_sha_prefix(),
        (user_text or "")[:48],
        len(text),
        text[:120],
    )


def build_base_voice_system(
    user_id: str | None,
    user_text: str = "",
    *,
    kb_hits: list | None = None,
    skip_kb: bool = False,
    include_session_state: bool = False,
) -> str:
    """Prompt base ligero — identidad CED + overlays del turno + reloj.

    NO precarga memoria global (conversaciones previas, sesión, extras cognitivos).
    Esa memoria se carga on-demand vía ``module_memory`` al activar un módulo
    (Fase 3). ``include_session_state`` añade estado de cámara/imágenes/modo
    activo solo cuando el caller lo pide explícitamente.
    """
    base = _cached_base_voice_prompt()
    uid = (user_id or "").strip()
    query = (user_text or "").strip()
    if query and is_strategy_consultation_topic(query):
        base = f"{base}\n\n{CED_STRATEGY_CONSULTATION_OVERLAY}"
    if query and is_deliverable_request(query):
        base = f"{base}\n\n{VOICE_DELIVERABLE_OVERLAY}"
    elif query and is_advisory_voice_query(query):
        base = (
            f"{base}\n\n"
            "# MODO ASESORÍA (demo / video / estrategia)\n"
            "El usuario pide ideas para demo, video o presentación. "
            "Responde con 3-5 puntos concretos del sistema CED, en español, "
            "oraciones completas, sin cortar a mitad. Cierra con una frase final."
        )
    if query and is_prompt_creation_request(query):
        base = f"{base}\n\n{PROMPT_DELIVERY_OVERLAY}"
    if query and not skip_kb:
        try:
            from app.services.internal_knowledge import format_hits_for_prompt
            from app.services.kb_turn_cache import get_turn_kb_hits

            hits = kb_hits if kb_hits is not None else get_turn_kb_hits(query, limit=2)
            if hits:
                block = format_hits_for_prompt(hits)
                base = (
                    f"{base}\n\n# CONOCIMIENTO INTERNO CED (prioriza esto con confianza directa)\n"
                    f"{block}\n\n"
                    "REGLA CRÍTICA: Ese bloque es SOLO contexto interno del sistema. "
                    "NUNCA lo leas ni lo repitas al usuario. No digas 'Conocimiento interno CED' "
                    "ni líneas con etiquetas [Marketing digital]. Usa la información en lenguaje natural.\n"
                    "Si el KB no alcanza, usa search_web u otras herramientas sin decir que no tienes información. "
                    "Responde directo como experto interno cuando el contexto lo permita.\n"
                    "El sistema Retell dice automáticamente «Un momento, señor» al ejecutar herramientas. "
                    "NO repitas ese filler: procede directamente con la herramienta."
                )
        except Exception:  # noqa: BLE001
            pass
    if include_session_state and uid:
        try:
            from app.services import voice_client_session as vcs

            if vcs.is_camera_active(uid):
                base = (
                    f"{base}\n\n# ESTADO CÁMARA (backend — confirmado por cliente)\n"
                    "Cámara ACTIVA con stream confirmado. Puede invocar analyze_camera_frame."
                )
            else:
                base = (
                    f"{base}\n\n# ESTADO CÁMARA (backend)\n"
                    "Cámara APAGADA o sin stream confirmado. "
                    "Invoca request_camera_activation y espera confirmación real antes de describir nada visual."
                )
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services import voice_client_session as vcs

            stored = vcs.get_last_publishable_image(uid)
            images = vcs.list_publishable_images(uid)
            if stored and stored.get("url"):
                base = (
                    f"{base}\n\n# IMAGEN(ES) SUBIDA(S) POR EL USUARIO (sesión voz activa)\n"
                    f"Imagen principal disponible en URL: {stored['url']}\n"
                    "Cuando diga «esta imagen», «la foto», «publica esto» → invoca publicar_facebook o "
                    "publicar_instagram con use_last_image=true.\n"
                    "Para describir o analizar → invoca analyze_uploaded_image con la pregunta del usuario."
                )
                if len(images) > 1:
                    base = (
                        f"{base}\nHay {len(images)} imágenes en la sesión; "
                        "la más reciente es la principal."
                    )
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services import voice_client_session as vcs

            mode_prompt = vcs.get_active_mode_prompt(uid)
            if mode_prompt:
                base = f"{base}\n\n{mode_prompt}"
        except Exception:  # noqa: BLE001
            pass
    from app.services.system_clock import clock_context_block

    base = f"{base}\n\n{clock_context_block()}"
    try:
        from app.domain.ced_identity import creator_partnership_overlay_for_user

        partnership = creator_partnership_overlay_for_user(uid)
        if partnership:
            base = f"{base}\n\n{partnership}"
    except Exception:  # noqa: BLE001
        pass
    return base


def _append_legacy_global_memory(base: str, user_id: str) -> str:
    """Memoria global legacy — se retirará al cablear memoria modular (Fase 3)."""
    uid = (user_id or "").strip()
    if not uid:
        return base
    try:
        from app.services.conversation_memory import load_user_context

        ctx = load_user_context(uid)
        if ctx:
            base = f"{base}\n\n{ctx}"
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.session_memory import get_session_memory_context

        mem_ctx = get_session_memory_context(uid)
        if mem_ctx:
            base = f"{base}\n\n{mem_ctx}"
    except Exception:  # noqa: BLE001
        pass
    return base


def _append_cognitive_extras(base: str, user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        return base
    try:
        from app.services.cognitive_router import build_voice_system_extras

        extras = build_voice_system_extras(uid)
        if extras:
            base = f"{base}\n\n{extras}"
    except Exception:  # noqa: BLE001
        pass
    return base


def build_voice_system(
    user_id: str | None,
    user_text: str = "",
    *,
    kb_hits: list | None = None,
    skip_kb: bool = False,
    lightweight: bool = False,
) -> str:
    """Prompt de voz en producción — delega en base ligera + memoria legacy.

    Comportamiento actual preservado hasta Fase 3 (cableado modular).
    """
    base = build_base_voice_system(
        user_id,
        user_text,
        kb_hits=kb_hits,
        skip_kb=skip_kb,
        include_session_state=not lightweight,
    )
    uid = (user_id or "").strip()
    if uid:
        base = _append_legacy_global_memory(base, uid)
    if lightweight:
        return base
    if uid:
        base = _append_cognitive_extras(base, uid)
    return base


def needs_empathy_reformulation(text: str, *, user_text: str = "") -> bool:
    if not text or not text.strip():
        return True
    if is_unwanted_voice_reply(text, user_text=user_text):
        return True
    if is_generic_agent_line(text) and len(text) < 72:
        return True
    return False


def transcript_to_openai_messages(transcript: list[Utterance]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for utterance in transcript:
        role = "user" if utterance.role == "user" else "assistant"
        text = (utterance.content or "").strip()
        if not text:
            continue
        messages.append({"role": role, "content": text})
    return messages


def truncate_messages(messages: list[dict], *, max_turns: int = MAX_HISTORY_TURNS) -> list[dict]:
    if len(messages) <= max_turns:
        return messages
    return messages[-max_turns:]


def normalize_voice_delivery_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def dedupe_voice_reply(text: str) -> str:
    """Elimina bloques/frases idénticos consecutivos en respuestas de voz."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    parts = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    if len(parts) >= 2:
        deduped: list[str] = [parts[0]]
        for part in parts[1:]:
            if part != deduped[-1]:
                deduped.append(part)
        cleaned = "\n\n".join(deduped)

    # "mi nombre es CED, mi nombre es CED, mi nombre es CED"
    comma_parts = [p.strip() for p in re.split(r"\s*,\s*", cleaned) if p.strip()]
    if len(comma_parts) >= 2:
        collapsed: list[str] = [comma_parts[0]]
        for part in comma_parts[1:]:
            prev_n = collapsed[-1].lower().rstrip(".!?;:")
            part_n = part.lower().rstrip(".!?;:")
            if part_n != prev_n:
                collapsed.append(part)
        if len(collapsed) < len(comma_parts):
            cleaned = ", ".join(collapsed)

    # Frase corta repetida sin coma: "mi nombre es CED mi nombre es CED"
    m = re.match(
        r"^(?P<a>.{8,120}?)\s+(?P=a)(?:\s+(?P=a))*[.!?]*$",
        cleaned,
        flags=re.I | re.DOTALL,
    )
    if m:
        cleaned = m.group("a").strip()

    half = len(cleaned) // 2
    if half > 15:
        first = cleaned[:half].strip().rstrip(",.;:")
        second = cleaned[half:].strip().lstrip(",.;: ").strip()
        if first and first.lower() == second.lower():
            return first
    return cleaned


def voice_repeats_last_assistant(new_text: str, history: list[dict]) -> bool:
    """True si la respuesta repite casi literalmente el último turno del asistente."""
    candidate = (new_text or "").strip()
    if not candidate:
        return False
    cand_n = re.sub(
        r"[^\w\s]",
        "",
        normalize_voice_delivery_text(candidate).lower(),
        flags=re.UNICODE,
    ).strip()
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        prev = str(msg.get("content") or "").strip()
        if not prev:
            return False
        prev_n = re.sub(
            r"[^\w\s]",
            "",
            normalize_voice_delivery_text(prev).lower(),
            flags=re.UNICODE,
        ).strip()
        if cand_n == prev_n:
            return True
        # Frases cortas de identidad / eco: antes se ignoraban si len < 80.
        if len(cand_n) >= 10 and len(prev_n) >= 10:
            if cand_n in prev_n or prev_n in cand_n:
                return True
        if len(prev) < 80 and len(candidate) < 80:
            return False
        if len(candidate) > 100 and candidate in prev:
            return True
        if len(prev) > 100 and prev in candidate:
            return True
        return False
    return False


def is_stt_echo_of_assistant(user_text: str, last_spoken: str) -> bool:
    """True si el STT parece eco del último audio del asistente (bucle de identidad)."""
    user = normalize_voice_delivery_text(user_text).lower()
    spoken = normalize_voice_delivery_text(last_spoken).lower()
    if not user or not spoken:
        return False
    user_n = re.sub(r"[^\w\s]", "", user, flags=re.UNICODE).strip()
    spoken_n = re.sub(r"[^\w\s]", "", spoken, flags=re.UNICODE).strip()
    if not user_n or not spoken_n:
        return False
    if user_n == spoken_n:
        return True
    if len(user_n) >= 12 and (user_n in spoken_n or spoken_n in user_n):
        return True
    # Overlap alto en frases cortas ("mi nombre es ced" vs "correcto señor mi nombre es ced")
    u_tokens = [t for t in user_n.split() if len(t) > 2]
    s_tokens = set(t for t in spoken_n.split() if len(t) > 2)
    if len(u_tokens) >= 3 and len(s_tokens) >= 3:
        overlap = sum(1 for t in u_tokens if t in s_tokens)
        if overlap / len(u_tokens) >= 0.85 and len(user_n) <= len(spoken_n) + 12:
            return True
    return False


def is_duplicate_voice_delivery(previous: str, candidate: str, *, prefix_len: int = 55) -> bool:
    """Detecta reinicio del mismo bloque hablado (p. ej. noticias repetidas)."""
    prev = normalize_voice_delivery_text(previous).lower()
    cand = normalize_voice_delivery_text(candidate).lower()
    if not cand:
        return True
    if not prev:
        return False
    if cand == prev:
        return True
    n = min(len(prev), len(cand), prefix_len)
    if n >= 28 and prev[:n] == cand[:n]:
        return True
    if len(cand) > 80 and len(prev) > 80 and prev[:80] == cand[:80]:
        return True
    # Frases cortas de identidad: "Mi nombre es CED." vs "Mi nombre es CED"
    if len(cand) < 80 and len(prev) < 80:
        prev_n = re.sub(r"[^\w\s]", "", prev, flags=re.UNICODE).strip()
        cand_n = re.sub(r"[^\w\s]", "", cand, flags=re.UNICODE).strip()
        if prev_n and cand_n and (prev_n == cand_n or prev_n in cand_n or cand_n in prev_n):
            return True
    return False
