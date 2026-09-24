"""Utilidades compartidas — capa LLM de voz Retell (OpenAI GPT-4.1 / legacy Gemini)."""

from __future__ import annotations

import re
import unicodedata

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

# Pedidos de voz que apuntan al chat escrito / guion — no inventar ni rellenar con FitLine.
_TEXT_CHAT_RECALL_RE = re.compile(
    r"(?:"
    r"lee(?:me|r)?\s+(?:lo\s+que|el\s+texto|el\s+guion|el\s+gui[oó]n|el\s+brief)|"
    r"(?:lo\s+que\s+)?(?:te\s+)?(?:envi[eé]|mand[eé]|escrib[ií]|peg[uú]e)\s+(?:por\s+)?(?:texto|chat|escrito)|"
    r"(?:en|del|por)\s+(?:el\s+)?chat(?:\s+de\s+texto)?|"
    r"guion(?:es)?|gui[oó]n(?:es)?|brief(?:ing)?|"
    r"lo\s+del\s+chat|mensaje(?:s)?\s+(?:del|de)\s+chat|"
    r"repet[ií](?:me)?\s+lo\s+que\s+(?:te\s+)?(?:envi|mand|escrib)|"
    r"qu[eé]\s+te\s+(?:envi[eé]|mand[eé]|escrib[ií])"
    r")",
    re.I,
)

_MISSING_TEXT_CHAT_OVERLAY = """
# CHAT DE TEXTO — SIN CONTENIDO DISPONIBLE
El usuario pide que lea/use algo que envió por texto o un guion, pero NO hay
mensajes de chat de texto ni puente en vivo en este turno.
OBLIGATORIO: dilo con honestidad en 1 frase (no lo tiene aquí) y pide que lo
pegue de nuevo en el chat o lo dicte.
PROHIBIDO inventar el guion, brief o texto.
PROHIBIDO rellenar con FitLine, PM International, prospección u otro tema
para «taparlo».
""".strip()

_BASE_VOICE_PROMPT: str | None = None


def wants_text_chat_recall(text: str) -> bool:
    """True si el turno de voz pide leer/usar lo enviado por chat o un guion."""
    t = (text or "").strip()
    if len(t) < 4:
        return False
    return bool(_TEXT_CHAT_RECALL_RE.search(t))


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
El usuario lleva un momento en silencio.
Di UNA sola frase corta de presencia — sin repetir ni retomar tu respuesta anterior.
Ejemplo: "Señor, quedo a la espera."
PROHIBIDO: repetir el último tema, volver a explicar, "Sigo atento", "¿Continuamos?", tono de chatbot.
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
    from app.services.deliverable_replies import needs_deliverable_token_budget

    if needs_deliverable_token_budget(user_text):
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
    omit_static_core: bool = False,
    omit_fitline_knowledge: bool = False,
) -> str:
    """Prompt base ligero — identidad CED + overlays del turno + reloj.

    NO precarga memoria global (conversaciones previas, sesión, extras cognitivos).
    Esa memoria se carga on-demand vía ``module_memory`` al activar un módulo
    (Fase 3). ``include_session_state`` añade estado de cámara/imágenes/modo
    activo solo cuando el caller lo pide explícitamente.

    omit_static_core / omit_fitline_knowledge: el caller usa Context Caching de
    Google para esos bloques (fitline_gemini_cache).
    """
    base = "" if omit_static_core else _cached_base_voice_prompt()
    uid = (user_id or "").strip()
    query = (user_text or "").strip()
    if query and is_strategy_consultation_topic(query):
        base = f"{base}\n\n{CED_STRATEGY_CONSULTATION_OVERLAY}" if base else CED_STRATEGY_CONSULTATION_OVERLAY
        from app.domain.ced_sales_marketing_playbook import (
            append_sales_marketing_playbook_if_needed,
        )

        base = append_sales_marketing_playbook_if_needed(base, query)
    if query:
        # Un «hazme un guion para un reel» no siempre entra por consultoría:
        # la plantilla de guiones se engancha aparte para cubrir también la voz.
        from app.domain.ced_script_blueprints import with_script_blueprints_if_needed

        base = with_script_blueprints_if_needed(base, query)
    # FitLine/PM: ficha SOLO si el turno es de ese tema (o modo guía activo).
    # Plan Cierre ya no fuerza la ficha en Excel/clima/etc. (evita puentes
    # fantasma tipo «Excel → Activize / Cell Energy»).
    inject_fitline = False
    guide_active = False
    recall_turn = bool(query and wants_text_chat_recall(query))
    if uid and query:
        try:
            from app.services import voice_client_session as vcs
            from app.services.opportunities_pilot.fitline_knowledge import (
                is_fitline_topic_suppressed_for,
                should_inject_fitline_for_turn,
            )

            guide_active = bool(vcs.is_fitline_guide_active(uid))
            inject_fitline = should_inject_fitline_for_turn(
                uid, query, guide_active=guide_active
            )
            # Continuidad: tras preguntas FitLine, follow-ups (expansión, etc.)
            # siguen con ficha — nunca Excel/clima ni con opt-out.
            if not inject_fitline and not is_fitline_topic_suppressed_for(uid):
                try:
                    from app.services.opportunities_pilot.fitline_close_trigger import (
                        _is_fitline_question,
                        get_engagement,
                    )

                    already = int(get_engagement(uid).get("question_count") or 0) > 0
                    if already and _is_fitline_question(
                        query, already_engaged=True
                    ):
                        inject_fitline = True
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            try:
                from app.services.opportunities_pilot.fitline_knowledge import (
                    wants_fitline_knowledge,
                )

                inject_fitline = wants_fitline_knowledge(query)
            except Exception:  # noqa: BLE001
                inject_fitline = False
    elif query:
        try:
            from app.services.opportunities_pilot.fitline_knowledge import (
                wants_fitline_knowledge,
            )

            inject_fitline = wants_fitline_knowledge(query)
        except Exception:  # noqa: BLE001
            inject_fitline = False
    if inject_fitline and recall_turn:
        try:
            from app.services.opportunities_pilot.fitline_knowledge import (
                wants_fitline_knowledge,
            )

            if not wants_fitline_knowledge(query):
                inject_fitline = False
        except Exception:  # noqa: BLE001
            inject_fitline = False
    if not omit_fitline_knowledge and inject_fitline:
        from app.services.opportunities_pilot.fitline_knowledge import (
            append_fitline_knowledge_if_needed,
        )

        base = append_fitline_knowledge_if_needed(
            base,
            query or "FitLine PM International",
            force=bool(guide_active and not recall_turn),
            user_id=uid or None,
        )
    # Cierre + foro: turnos FitLine o follow-ups cortos con engagement previo.
    # Nunca por engagement residual si el usuario optó por fuera del tema.
    if uid and query:
        fitline_turn = inject_fitline
        if not fitline_turn:
            try:
                from app.services.opportunities_pilot.fitline_close_trigger import (
                    _is_fitline_question,
                    get_engagement,
                )
                from app.services.opportunities_pilot.fitline_knowledge import (
                    is_fitline_topic_suppressed_for,
                )

                if not is_fitline_topic_suppressed_for(uid):
                    already = int(get_engagement(uid).get("question_count") or 0) > 0
                    fitline_turn = _is_fitline_question(
                        query, already_engaged=already
                    )
            except Exception:  # noqa: BLE001
                fitline_turn = False
        if fitline_turn:
            try:
                from app.services.opportunities_pilot.fitline_close_trigger import (
                    append_fitline_close_trigger_if_needed,
                )

                base = append_fitline_close_trigger_if_needed(base, uid, query)
            except Exception:  # noqa: BLE001
                pass
        try:
            from app.services.insight_questions import capture_insight_question

            capture_insight_question(uid, query, channel="voice")
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.services.user_session_profile import touch_and_learn

            touch_and_learn(uid, query, channel="voice")
        except Exception:  # noqa: BLE001
            pass
    # Modo Guía FitLine: mentor paso a paso (voz corta). Respeta opt-out de tema.
    if uid and query:
        try:
            from app.services.opportunities_pilot.fitline_guide_mode import (
                append_fitline_guide_if_needed,
            )
            from app.services.opportunities_pilot.fitline_knowledge import (
                is_fitline_topic_suppressed_for,
            )

            if not is_fitline_topic_suppressed_for(uid):
                base = append_fitline_guide_if_needed(
                    base,
                    uid,
                    query,
                    channel="voice",
                )
        except Exception:  # noqa: BLE001
            pass
    if query and is_deliverable_request(query):
        base = f"{base}\n\n{VOICE_DELIVERABLE_OVERLAY}"
    else:
        try:
            from app.services.deliverable_replies import (
                DELIVERABLE_FINISH_OVERLAY,
                is_deliverable_continuation_turn,
            )

            if is_deliverable_continuation_turn(query):
                base = f"{base}\n\n{VOICE_DELIVERABLE_OVERLAY}\n\n{DELIVERABLE_FINISH_OVERLAY}"
        except Exception:  # noqa: BLE001
            pass
    if query and is_advisory_voice_query(query) and "ENTREGA COMPLETA" not in (base or ""):
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
                    "Si el KB no alcanza Y NO es FitLine/PM cubierto por Oportunidades, "
                    "usa search_web u otras herramientas sin decir que no tienes información. "
                    "Responde directo como experto interno cuando el contexto lo permita.\n"
                    "FitLine/PM/productos PM: NUNCA search_web ni «investigando» si hay bloque Oportunidades.\n"
                    "El sistema dice automáticamente «Un momento, señor» al ejecutar herramientas. "
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
    omit_static_core: bool = False,
    omit_fitline_knowledge: bool = False,
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
        omit_static_core=omit_static_core,
        omit_fitline_knowledge=omit_fitline_knowledge,
    )
    uid = (user_id or "").strip()
    query = (user_text or "").strip()
    recall = wants_text_chat_recall(query) if query else False
    if uid:
        base = _append_legacy_global_memory(base, uid)
        studio = ""
        try:
            from app.services.voice_client_session import format_studio_chat_overlay

            studio = format_studio_chat_overlay(uid) or ""
            if studio:
                base = f"{base}\n\n{studio}"
        except Exception:
            studio = ""
        # Pedido explícito de leer/usar el chat o guion → cargar canal texto.
        if recall:
            try:
                from app.services.conversation_memory import (
                    format_text_chat_for_voice_overlay,
                )

                text_overlay = format_text_chat_for_voice_overlay(uid)
                if text_overlay and text_overlay not in base:
                    base = f"{base}\n\n{text_overlay}"
                elif not studio and not text_overlay:
                    base = f"{base}\n\n{_MISSING_TEXT_CHAT_OVERLAY}"
            except Exception:
                if not studio:
                    base = f"{base}\n\n{_MISSING_TEXT_CHAT_OVERLAY}"
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


_CED_NAME_TOKEN = re.compile(r"^(?:ced|c\.e\.d\.?)$", re.I)
_IDENTITY_FILLER = frozenset(
    {
        "ced",
        "c",
        "e",
        "d",
        "mi",
        "me",
        "nombre",
        "es",
        "llamo",
        "soy",
        "correcto",
        "senor",
        "señor",
        "si",
        "sí",
        "claro",
        "ok",
        "vale",
    }
)
_SHORT_WORD_STUTTER = re.compile(
    r"^(?P<w>\w{2,16})(?:[\s,.;:]+(?P=w)){2,}[.!?]*$",
    re.I,
)


def _fold_voice_tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFD", normalize_voice_delivery_text(text).lower())
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    folded = re.sub(r"[^\w\s]", " ", folded, flags=re.UNICODE)
    return [tok for tok in folded.split() if tok]


def is_identity_name_stutter(text: str) -> bool:
    """True si el turno es solo el nombre CED (o 'CED CED CED'), no una pregunta real."""
    tokens = _fold_voice_tokens(text)
    if not tokens:
        return False
    ced_n = sum(1 for tok in tokens if _CED_NAME_TOKEN.match(tok))
    if ced_n >= 2 and all(tok in _IDENTITY_FILLER or _CED_NAME_TOKEN.match(tok) for tok in tokens):
        return True
    if len(tokens) == 1 and _CED_NAME_TOKEN.match(tokens[0]):
        return True
    # STT a veces deletrea C-E-D como letras sueltas.
    if len(tokens) >= 3 and all(tok in {"c", "e", "d", "ced"} for tok in tokens):
        return True
    joined = " ".join(tokens)
    stutter = _SHORT_WORD_STUTTER.match(joined)
    if stutter and _CED_NAME_TOKEN.match(stutter.group("w")):
        return True
    return False


def is_ced_name_echo(user_text: str, last_spoken: str = "") -> bool:
    """Eco STT de 'CED' / 'CED CED CED' tras hablar del nombre."""
    tokens = _fold_voice_tokens(user_text)
    if not tokens:
        return False
    if not all(_CED_NAME_TOKEN.match(tok) for tok in tokens):
        return False
    if len(tokens) >= 2:
        return True
    spoken = " ".join(_fold_voice_tokens(last_spoken))
    return "ced" in spoken.split()


def dedupe_voice_reply(text: str) -> str:
    """Elimina bloques/frases idénticos consecutivos en respuestas de voz."""
    cleaned = collapse_stacked_response_variants((text or "").strip())
    if not cleaned:
        return cleaned
    # Ráfaga 'CED CED CED' (el bucle de identidad no usaba comas).
    cleaned = re.sub(r"(?i)\bced(?:[\s,.;:]+ced)+\b", "CED", cleaned)
    stutter = _SHORT_WORD_STUTTER.match(re.sub(r"[.!?]+$", "", cleaned).strip())
    if stutter:
        cleaned = stutter.group("w")
    if is_identity_name_stutter(cleaned):
        return "Soy CED."
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


def collapse_stacked_response_variants(text: str) -> str:
    """Si el modelo apiló 2 versiones de la misma respuesta, conserva una sola.

    Casos: delimitadores <<<>>>, reinicios «Mire,…», o dos bloques/párrafos casi iguales.
    """
    raw = (text or "").strip()
    if not raw:
        return raw

    # Quitar marcas de TTS / instrucciones filtradas.
    raw = re.sub(r"<{2,}|}>{2,}", " ", raw)
    raw = re.sub(r"\bFRASE\s*:\s*", " ", raw, flags=re.I)
    raw = re.sub(r"\bFIN\b\.?", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw).strip()

    # Párrafos duplicados (mismo bloque emitido 2 veces — gasto de texto sin audio útil).
    paras = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
    if len(paras) >= 2:
        kept: list[str] = []
        seen_norm: list[str] = []
        for p in paras:
            pn = _normalize_for_repeat_compare(p)
            if len(pn) < 40:
                kept.append(p)
                continue
            dup = False
            for prev in seen_norm:
                if pn == prev or (len(pn) > 60 and (pn[:80] == prev[:80] or pn in prev or prev in pn)):
                    dup = True
                    break
            if dup:
                continue
            kept.append(p)
            seen_norm.append(pn)
        if kept:
            raw = "\n\n".join(kept) if "\n\n" in (text or "") else " ".join(kept)

    # Partir por reinicios típicos de «segunda versión».
    splitters = re.split(
        r"(?=(?:\bMire[,.]?\s+[A-ZÁÉÍÓÚÑ])|(?:\bClaro[,.]?\s+(?:señor|señora|mire))|(?:\bPerfecto[,.]?\s+(?:señor|señora)))",
        raw,
        flags=re.I,
    )
    chunks = [c.strip(" \n\r\t-—") for c in splitters if c and len(c.strip()) >= 24]
    if len(chunks) >= 2:
        # Quedarse con el bloque más completo (suele ser el último o el más largo).
        best = max(chunks, key=lambda c: (c.rstrip().endswith((".", "!", "?")), len(c)))
        # Si el primero es claramente un saludo/relleno corto y el segundo es la respuesta…
        if len(chunks[0]) < 120 and len(chunks[-1]) > len(chunks[0]) * 1.4:
            best = chunks[-1]
        raw = best

    # Dos mitades casi iguales (variante A + variante B del mismo largo).
    if len(raw) >= 160:
        mid = len(raw) // 2
        # Buscar frontera cerca del medio.
        window = raw[mid - 40 : mid + 40]
        cut = None
        for sep in (". ", "? ", "! ", "\n"):
            i = window.find(sep)
            if i != -1:
                cut = mid - 40 + i + len(sep)
                break
        if cut and 40 < cut < len(raw) - 40:
            a = raw[:cut].strip()
            b = raw[cut:].strip()
            if len(a) >= 60 and len(b) >= 60:
                a_n = _normalize_for_repeat_compare(a[:180])
                b_n = _normalize_for_repeat_compare(b[:180])
                # Misma apertura ≈ dos versiones apiladas.
                if a_n and b_n and (a_n[:40] == b_n[:40] or a_n in b_n or b_n in a_n):
                    raw = b if len(b) >= len(a) else a

    # Oraciones consecutivas casi idénticas.
    sentences = re.split(r"(?<=[.!?…])\s+", raw)
    if len(sentences) >= 2:
        out_s: list[str] = []
        for s in sentences:
            sn = _normalize_for_repeat_compare(s)
            if (
                out_s
                and len(sn) >= 50
                and _normalize_for_repeat_compare(out_s[-1])[:70] == sn[:70]
            ):
                continue
            out_s.append(s)
        raw = " ".join(out_s).strip()

    return raw.strip()


def prefer_single_voice_variant(primary: str, secondary: str) -> str:
    """Al completar un turno truncado: no apilar dos versiones completas."""
    a = (primary or "").strip()
    b = (secondary or "").strip()
    if not b:
        return a
    if not a:
        return b
    a_n = _normalize_for_repeat_compare(a)
    b_n = _normalize_for_repeat_compare(b)
    if not a_n or not b_n:
        return f"{a.rstrip('.')} {b.lstrip()}".strip()
    # Continuación = reescritura completa → quedarse con una.
    if b_n.startswith(a_n[: min(80, len(a_n))]) or a_n.startswith(b_n[: min(80, len(b_n))]):
        return b if len(b) >= len(a) else a
    if a_n[:50] == b_n[:50] and abs(len(a) - len(b)) < max(80, len(a) * 0.35):
        return b if len(b) >= len(a) else a
    # Continuación corta de remate.
    if len(b) < max(100, int(len(a) * 0.55)):
        return f"{a.rstrip('.')} {b.lstrip()}".strip()
    # Continuación parece otro monólogo → preferir la más completa.
    if re.match(r"^(?:mire|claro|perfecto|bueno|hola)\b", b.lower()):
        return b if len(b) >= len(a) * 0.8 else a
    return collapse_stacked_response_variants(f"{a.rstrip('.')} {b.lstrip()}".strip())


def _normalize_for_repeat_compare(text: str) -> str:
    return re.sub(
        r"[^\w\s]",
        "",
        normalize_voice_delivery_text(text).lower(),
        flags=re.UNICODE,
    ).strip()


def last_assistant_content(history: list[dict] | None, *, min_len: int = 80) -> str:
    """Último turno assistant/model con texto útil."""
    for msg in reversed(history or []):
        role = str(msg.get("role") or "").lower()
        if role not in ("assistant", "model"):
            continue
        prev = str(msg.get("content") or "").strip()
        if len(prev) >= min_len:
            return prev
    return ""


def strip_embedded_prior_assistant(
    new_text: str,
    history: list[dict] | None,
) -> str:
    """Quita el bloque del turno anterior si el modelo lo re-emite antes de lo nuevo.

    Causa típica: respuesta Activize completa + inicio de Restorate → se corta
    lo nuevo por límite de tokens.
    """
    text = (new_text or "").strip()
    prev = last_assistant_content(history, min_len=80)
    if not text or not prev:
        return text
    if text == prev:
        return text

    # Prefijo literal del mensaje anterior.
    if text.startswith(prev):
        rest = text[len(prev) :].lstrip(" \n\r\t.,;:—-")
        if len(rest) >= 24:
            return rest

    prev_n = _normalize_for_repeat_compare(prev)
    text_n = _normalize_for_repeat_compare(text)
    if len(prev_n) < 80 or len(text_n) <= len(prev_n) + 20:
        return text

    # El texto nuevo empieza con ~el mensaje anterior (normalizado).
    if text_n.startswith(prev_n[: min(400, len(prev_n))]):
        # Recortar por longitud aproximada del bloque previo en el original.
        cut = min(len(text), max(len(prev), int(len(text) * (len(prev_n) / max(len(text_n), 1)))))
        # Buscar frontera de frase tras el solapamiento.
        probe = text[cut : cut + 120] if cut < len(text) else ""
        for sep in (". ", "? ", "! ", "\n"):
            idx = text.find(sep, max(0, cut - 40))
            if idx != -1 and idx < cut + 80:
                rest = text[idx + len(sep) :].strip()
                if len(rest) >= 24:
                    return rest
        rest = text[cut:].lstrip(" \n\r\t.,;:—-")
        if len(rest) >= 24:
            return rest

    # Contención: prev completo embebido cerca del inicio (preámbulo corto).
    idx = text.find(prev)
    if idx != -1 and idx < 80 and len(text) > len(prev) + 24:
        rest = text[idx + len(prev) :].lstrip(" \n\r\t.,;:—-")
        if len(rest) >= 24:
            return rest

    return text


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
    if is_ced_name_echo(user_text, last_spoken):
        return True
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
    # Incluye tokens de 3 letras (CED); el umbral >2 dejaba pasar el bucle.
    u_tokens = [t for t in user_n.split() if len(t) >= 3]
    s_tokens = set(t for t in spoken_n.split() if len(t) >= 3)
    if len(u_tokens) >= 2 and s_tokens:
        overlap = sum(1 for t in u_tokens if t in s_tokens)
        if overlap / len(u_tokens) >= 0.62:
            return True
    return False


def is_near_duplicate_user_turn(previous: str, incoming: str) -> bool:
    """True si el STT reenvió la misma pregunta con variación mínima (bucle de turno)."""

    def _key(text: str) -> str:
        folded = unicodedata.normalize("NFD", (text or "").lower())
        folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^\w\s]", " ", folded, flags=re.UNICODE)

    a = " ".join(_key(previous).split())
    b = " ".join(_key(incoming).split())
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 10 and len(b) >= 10 and (a in b or b in a):
        return True
    a_tokens = [t for t in a.split() if len(t) > 2]
    b_set = {t for t in b.split() if len(t) > 2}
    if len(a_tokens) >= 4 and len(b_set) >= 4:
        overlap = sum(1 for t in a_tokens if t in b_set)
        if overlap / max(len(a_tokens), len(b_set)) >= 0.78:
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
