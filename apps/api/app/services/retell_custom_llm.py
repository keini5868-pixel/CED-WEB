"""Utilidades del protocolo Retell Custom LLM."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

logger = logging.getLogger(__name__)

from app.services.cognitive_intents import (
    is_advanced_request,
    is_camera_voice_command,
    is_internal_knowledge_query,
    is_meta_publish_intent,
    is_personal_vent_intent,
    is_script_demo_request,
    is_news_intent,
    is_volatile_query,
    is_weather_intent,
    is_web_research_intent,
    normalize_text,
    requires_live_web,
)
from app.services.retell_llm_types import Utterance
from app.services.voice_spoken import VOICE_SPOKEN_MAX_CHARS, fit_voice_spoken

_STT_ECHO_FRAGMENTS = frozenset(
    {
        "a su",
        "usted",
        "en que puedo",
        "en qué puedo",
        "como orden",
        "cómo orden",
        "la",
        "el",
        "los",
        "las",
        "y",
        "que",
        "qué",
    }
)

_INAUDIBLE_STT = re.compile(
    r"\b(inaudible|unintelligible|indiscernible|mumbling)\b|\(\s*inaudible",
    re.I,
)

_TV_NOISE_STT = re.compile(
    r"\bsecci[oó]n de la econom[ií]a\b|\bnoticias del d[ií]a\b|\bultima hora\b",
    re.I,
)

_ECHO_USER_LINES = frozenset(
    {
        "a su servicio, señor",
        "a su servicio señor",
        "a su servicio, señor.",
        "a su servicio señor.",
    }
)

_SMALL_TALK = frozenset(
    {
        "hola",
        "hola cómo estás",
        "hola como estas",
        "hola, ¿cómo estás?",
        "hola, como estas?",
        "buenos días",
        "buenas tardes",
        "buenas noches",
        "cómo estás",
        "como estas",
        "qué tal",
        "que tal",
        "okay",
        "ok",
        "sí",
        "si",
    }
)

_GENERIC_AGENT_LINES = frozenset(
    {
        "operativo y a su servicio, señor.",
        "operativo y a su servicio señor.",
        "a su servicio, señor.",
    }
)

_ACK_ONLY = frozenset({"ok", "okay", "sí", "si", "vale", "bien", "yes", "news", "noticias"})

# Palabras de asentimiento / cierre de turno — combinables en frases cortas
# como "ok perfecto", "muy bien", "de acuerdo", "sí gracias", "todo bien".
_ACK_CLOSING_WORDS = frozenset(
    {
        "ok", "okay", "okey", "vale", "dale", "listo", "perfecto", "perfe",
        "genial", "excelente", "buenisimo", "gracias", "muchas", "muy",
        "bien", "esta", "está", "de", "acuerdo", "entendido", "entiendo",
        "correcto", "si", "sí", "claro", "asi", "así", "es", "todo",
        "sale", "chevere", "chévere", "va", "listindo",
    }
)


def _is_closing_ack(text: str) -> bool:
    """True si el turno es solo asentimiento/cierre ('ok perfecto', 'muy bien')."""
    norm = _normalize(text)
    if not norm:
        return False
    if norm in _ACK_ONLY:
        return True
    tokens = norm.split()
    if not tokens or len(tokens) > 3:
        return False
    return all(tok in _ACK_CLOSING_WORDS for tok in tokens)

_WEB_FRAGMENT_HINTS = re.compile(
    r"\b(busca|buscar|buscame|investiga|precio|cotiza|clima|tiempo|temperatura|"
    r"noticia|ultim|dime|dame|cuanto|cuesta|hoy|internet|google|web|mercado|"
    r"tendencia|actualidad|significa|vale|creatina|suplemento)\b",
    re.I,
)

_FRAGMENT_PREFIX = re.compile(
    r"^(de|del|la|el|los|las|en|con|para|y|que|qué|en\s+estados)\b",
    re.I,
)


def _normalize(text: str) -> str:
    return normalize_text(text).rstrip(".,!?¿¡")


def _user_lines(transcript: list[Utterance]) -> list[str]:
    return [
        (u.content or "").strip()
        for u in transcript
        if u.role == "user" and (u.content or "").strip()
    ]


def last_user_text(transcript: list[Utterance]) -> str:
    lines = _user_lines(transcript)
    return lines[-1] if lines else ""


def merged_user_query(transcript: list[Utterance], *, max_lines: int = 2) -> str:
    """Une solo fragmentos cortos del mismo turno — no arrastra temas viejos."""
    lines = _user_lines(transcript)
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    last = lines[-1]
    prev = lines[-2]
    if _is_fragment_continuation(last, prev):
        return f"{prev} {last}".strip()
    return last


def _is_fragment_continuation(last: str, prev: str) -> bool:
    """True solo si `last` completa la frase anterior (ej. 'de Estados Unidos')."""
    ln = _normalize(last)
    pn = _normalize(prev)
    if not ln or not pn:
        return False
    if ln in _ACK_ONLY or pn in _ACK_ONLY:
        return False
    # Un cierre/asentimiento ("ok perfecto", "muy bien") NO continúa la consulta previa.
    if _is_closing_ack(last):
        return False
    if _needs_internet_lookup(last) and not _FRAGMENT_PREFIX.search(ln):
        if is_news_intent(last) or is_weather_intent(last) or is_web_research_intent(last):
            return False
    if len(ln.split()) <= 4 and _FRAGMENT_PREFIX.search(ln):
        return True
    if len(ln.split()) <= 2 and _needs_internet_lookup(pn):
        return True
    return False


def _needs_internet_lookup(text: str) -> bool:
    from app.services.opportunities_pilot.fitline_knowledge import prefers_fitline_over_web

    if prefers_fitline_over_web(text):
        return False
    if is_internal_knowledge_query(text) or is_personal_vent_intent(text):
        return False
    if is_weather_intent(text) or is_news_intent(text):
        return True
    if is_web_research_intent(text):
        return True
    if requires_live_web(text):
        return True
    norm = normalize_text(text)
    if len(norm) < 4 or norm in _ACK_ONLY:
        return False
    if is_volatile_query(text) and _WEB_FRAGMENT_HINTS.search(norm):
        return (
            is_news_intent(text)
            or is_weather_intent(text)
            or is_web_research_intent(text)
        )
    return False


def _web_kind_for(text: str) -> str:
    if is_weather_intent(text):
        return "weather"
    if is_news_intent(text):
        return "news"
    return "general"


def resolve_web_search_request(
    user_text: str,
    transcript: list[Utterance],
) -> dict[str, str] | None:
    """Detecta búsqueda web usando el último turno — sin mezclar noticias previas."""
    last = (user_text or "").strip()
    if not last or _normalize(last) in _ACK_ONLY:
        return None
    # Confirmaciones/cierres ("ok perfecto", "gracias") cierran turno — no re-buscan.
    if _is_closing_ack(last):
        return None
    if is_personal_vent_intent(last):
        return None

    lines = _user_lines(transcript)
    prev = lines[-2] if len(lines) >= 2 else ""

    if prev and _is_fragment_continuation(last, prev):
        query = f"{prev} {last}".strip()
        intent_source = query
    else:
        query = last
        intent_source = last

    if not _needs_internet_lookup(intent_source):
        return None

    kind = _web_kind_for(intent_source)
    if kind == "news" and not is_news_intent(intent_source):
        kind = "general"

    return {"kind": kind, "query": query}


DEFAULT_SCRIPT_TOPIC = (
    "Guion de 25 segundos para video presentando el sistema CED "
    "(Castillo de la Evolución Digital) y sus características principales."
)


def _is_pure_ack(text: str) -> bool:
    norm = _normalize(text)
    if norm in _ACK_ONLY:
        return True
    return bool(re.fullmatch(r"(s[ií]|ok|vale|dale|adelante|de acuerdo|confirma(do)?)", norm))


def is_inaudible_or_noise(text: str) -> bool:
    """Ruido de TV, silencio mal transcrito o fragmentos vacíos — no responder."""
    raw = (text or "").strip()
    if not raw:
        return True
    if _INAUDIBLE_STT.search(raw):
        return True
    if _TV_NOISE_STT.search(raw):
        return True
    norm = _normalize(raw)
    if norm in _STT_ECHO_FRAGMENTS:
        return True
    if len(norm.split()) == 1 and len(norm) <= 3:
        return True
    return False


def transcript_has_meta_publish_context(transcript: list[Utterance]) -> bool:
    """True si el turno reciente trata de publicar en redes, no de guion."""
    for line in _user_lines(transcript)[-8:]:
        if is_meta_publish_intent(line):
            return True
        norm = _normalize(line)
        if re.search(r"\b(imagen|foto|adjunt|chat|enlace|whatsapp)\b", norm) and re.search(
            r"\b(instagram|facebook|publica|publicar|postea)\b",
            norm,
        ):
            return True
    return False


def resolve_meta_publish_request(
    user_text: str,
    transcript: list[Utterance] | None = None,
) -> dict[str, str] | None:
    """Publicación en Meta solo tras confirmación explícita del usuario."""
    from app.services.publish_text import (
        extract_confirmed_publish_caption,
        is_publish_confirm,
        sanitize_publish_caption,
        validate_caption,
        detect_publish_platform,
    )

    last = (user_text or "").strip()
    if not last or not is_publish_confirm(last, allow_short_yes=True):
        return None
    platform = _detect_publish_platform_from_transcript(transcript or [], last)
    caption = extract_confirmed_publish_caption(transcript or [], platform=platform)
    if not caption:
        logger.info("[PUBLISH] bypass omitido: sin caption acordado en transcript")
        return None
    is_valid, reason = validate_caption(caption)
    if not is_valid:
        logger.info("[PUBLISH] bypass omitido caption inválido: %s", reason)
        return None
    return {
        "platform": platform,
        "caption": sanitize_publish_caption(caption),
    }


def _detect_publish_platform_from_transcript(
    transcript: list[Utterance],
    user_text: str,
) -> str:
    from app.services.publish_text import detect_publish_platform_explicit

    for utterance in reversed(transcript[-16:]):
        content = (utterance.content or "").strip()
        if not content:
            continue
        explicit = detect_publish_platform_explicit(content)
        if explicit:
            return explicit
    explicit = detect_publish_platform_explicit(user_text)
    if explicit:
        return explicit
    return "facebook"


_SOCIAL_COMMENT_UNSUPPORTED = re.compile(
    r"\b(github|twitter|x\.com|tiktok|youtube|whatsapp|telegram|linkedin|discord)\b",
    re.I,
)


def is_social_comment_read_intent(text: str) -> bool:
    last = (text or "").strip()
    if len(last) < 8:
        return False
    if _SOCIAL_COMMENT_UNSUPPORTED.search(last) and re.search(r"\bcomentarios?\b", last, re.I):
        return False
    has_platform = bool(
        re.search(r"\b(instagram|facebook|meta|redes|ig|fb)\b", last, re.I)
    )
    has_comment_cue = bool(
        re.search(r"\bcomentarios?\b", last, re.I)
        or re.search(
            r"\b(revisa|revisar|revisate|revis[aá]me|revisalo|checa|mira|lee|leer|listado|lista)\b",
            last,
            re.I,
        )
        or re.search(r"\b(nuevos?|recientes?)\b", last, re.I)
        or re.search(r"\bdime\s+s[ií]\b", last, re.I)
        or re.search(r"\btengo\b.*\b(nuevos?|comentarios?)\b", last, re.I)
    )
    if has_platform and has_comment_cue:
        return True
    return bool(re.search(r"\bcomentarios?\b", last, re.I) and has_comment_cue)


def social_comment_platform(text: str) -> str:
    norm = (text or "").lower()
    ig = bool(re.search(r"\b(instagram|ig)\b", norm))
    fb = bool(re.search(r"\b(facebook|fb)\b", norm))
    if ig and not fb:
        return "instagram"
    if fb and not ig:
        return "facebook"
    return "both"


def resolve_social_comments_request(user_text: str) -> dict[str, str] | None:
    """Lectura directa de comentarios — prioridad sobre narración del LLM."""
    last = (user_text or "").strip()
    if not last or not is_social_comment_read_intent(last):
        return None
    return {"platform": social_comment_platform(last)}


_AGENT_AWAITING_CAPTION = re.compile(
    r"imagen recibida|qu[eé] texto desea|texto desea que acompa[nñ]|"
    r"mensaje.*publicaci|descripci[oó]n.*instagram|qu[eé] desea publicar|"
    r"acompa[nñ]e su publicaci|necesito una imagen para instagram",
    re.I,
)


def agent_awaiting_instagram_caption(transcript: list[Utterance]) -> bool:
    for utterance in reversed(transcript):
        if utterance.role == "user":
            continue
        content = (utterance.content or "").strip()
        if content and _AGENT_AWAITING_CAPTION.search(content):
            return True
    return False


def resolve_instagram_caption_request(
    user_text: str,
    transcript: list[Utterance],
    *,
    user_id: str | None = None,
) -> dict[str, str] | None:
    """Tras 'Imagen recibida, ¿qué texto…?' — el siguiente turno es el caption."""
    last = (user_text or "").strip()
    if not last or is_inaudible_or_noise(last):
        return None
    if _is_pure_ack(last) and len(_normalize(last).split()) <= 2:
        return None

    from app.services import voice_client_session as vcs

    has_image = bool(user_id and vcs.get_last_publishable_image(user_id))
    awaiting = agent_awaiting_instagram_caption(transcript)
    if user_id and vcs.is_awaiting_instagram_caption(user_id):
        awaiting = True

    if not awaiting and not has_image:
        return None
    if not awaiting:
        norm = _normalize(last)
        if not re.search(
            r"\b(pon|pongas|ponle|texto|diga|digas|llegado|lleg[oó]|sistema|publica)\b",
            norm,
        ):
            return None

    caption = last
    for pat in (
        r"(?:quiero que (?:le )?)?(?:pongas|ponle|escribe|di(?:ga)?)\s+(?:que\s+)?(.+)$",
        r"(?:el texto es|texto:|caption:)\s*(.+)$",
    ):
        m = re.search(pat, last, re.I)
        if m and m.group(1).strip():
            caption = m.group(1).strip(" .,:;-")
            break
    if not caption or is_inaudible_or_noise(caption):
        return None
    return {"platform": "instagram", "caption": caption}


def is_unwanted_voice_reply(text: str, *, user_text: str = "") -> bool:
    """Detecta relleno tipo chatbot o re-preguntas de confirmación."""
    if is_generic_agent_line(text):
        return True
    norm = _normalize(text)
    if re.search(r"sigo atento|continuamos|en qu[eé] m[aá]s puedo", norm):
        return True
    if user_text and (_needs_internet_lookup(user_text) or is_web_research_intent(user_text)):
        if re.search(
            r"keini castillo es el creador|su proposito es ayudar a las personas a desarrollar|"
            r"repeticion en contexto estable refuerza conexiones neuronales",
            norm,
        ):
            return True
        from app.services.internal_kb_guard import contains_internal_kb_leak

        if contains_internal_kb_leak(text):
            return True
    return False


def promised_voice_search_without_result(text: str, *, user_text: str = "") -> bool:
    """True si promete buscar/investigar sin entregar resultado sustantivo."""
    t = (text or "").strip()
    if not t:
        return False
    promised = bool(
        re.search(
            r"\b(buscar[eé]|voy a buscar|investigar[eé]|voy a investigar|"
            r"consultar[eé] en internet|d[eé]jame buscar|perm[ií]teme buscar|"
            r"un momento.*buscar|perm[ií]tame.*investigar)\b",
            t,
            re.I,
        )
    )
    if not promised:
        return False
    substantive = len(re.sub(r"[^a-záéíóúñA-ZÁÉÍÓÚÑ0-9]", "", t)) > 80
    if substantive:
        return False
    if user_text and (_needs_internet_lookup(user_text) or is_web_research_intent(user_text)):
        return True
    return False


def resolve_camera_voice_request(user_text: str) -> str | None:
    """Tool de cámara a ejecutar, o None."""
    last = (user_text or "").strip()
    if not last or not is_camera_voice_command(last):
        return None
    norm = _normalize(last)
    if re.search(r"\b(apaga|desactiva|cierra|deja de mirar)\b", norm):
        return "request_camera_deactivation"
    if re.search(
        r"\b(qu[eé]\s+ves|qu[eé] veo|mira|analiza|visi[oó]n|busca.*visible|mostrando|"
        r"ves\?|dime qu[eé] ves|cu[eé]ntame qu[eé] ves|observas)\b",
        norm,
    ):
        if re.search(r"\bbusca|internet|google|web\b", norm):
            return "buscar_lo_visible"
        return "analyze_camera_frame"
    return "request_camera_activation"


def _current_turn_wants_script(user_text: str) -> bool:
    last = (user_text or "").strip()
    if not last or _is_pure_ack(last):
        return False
    return is_script_demo_request(last) or (
        is_advanced_request(last) and not is_camera_voice_command(last)
    )


def should_clear_pending_script(user_text: str) -> bool:
    """True si el turno actual NO es guion ni confirmación de guion."""
    last = (user_text or "").strip()
    if not last:
        return False
    if is_meta_publish_intent(last):
        return True
    if is_camera_voice_command(last):
        return True
    if resolve_web_search_request(last, []) is not None:
        return True
    if _is_concept_question(last):
        return True
    if _current_turn_wants_script(last):
        return False
    return True


def remember_pending_script_topic(
    call_id: str,
    transcript: list[Utterance],
    *,
    user_text: str,
    set_pending: Callable[[str, str], None],
    script_already_delivered: bool = False,
) -> None:
    """Guarda el tema del guion solo si el turno ACTUAL lo pide (no reescanea historial)."""
    last = (user_text or "").strip()
    if not last or _is_pure_ack(last):
        return
    if script_already_delivered and not _current_turn_wants_script(last):
        return
    if is_camera_voice_command(last):
        return
    if _current_turn_wants_script(last):
        set_pending(call_id, last)


def split_progressive_voice(text: str, *, topic: str) -> list[tuple[str, bool]]:
    """Parte respuestas largas de guion en bloques secuenciales (sin solaparse)."""
    from app.services.deliverable_replies import is_deliverable_request
    from app.services.voice_spoken import (
        is_advisory_voice_query,
        split_voice_delivery_chunks,
        voice_spoken_limit,
    )

    limit = voice_spoken_limit(topic)
    cleaned = fit_voice_spoken(" ".join((text or "").split()).strip(), max_chars=limit)
    if not cleaned:
        return []
    if is_deliverable_request(topic) and len(cleaned) > 520:
        return split_voice_delivery_chunks(cleaned)
    if not is_advisory_voice_query(topic) or len(cleaned) <= 520:
        return [(cleaned, True)]

    chunk = cleaned[:560]
    last_end = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
    if last_end < 180:
        return [(cleaned, True)]
    first = cleaned[: last_end + 1].strip()
    second = cleaned[last_end + 1 :].strip()
    if not second:
        return [(cleaned, True)]
    return [(first, False), (second, True)]


def web_search_hold_phrase(kind: str) -> str:
    """Frase de espera — solo noticias/clima (mensaje aparte antes del resultado)."""
    if kind == "weather":
        return "Un momento, señor. Consulto el clima."
    if kind == "news":
        return "Un momento, señor. Consulto las noticias."
    return "Un momento, señor."


def format_web_delivery(kind: str, spoken: str) -> str:
    from app.services.voice_spoken import finalize_voice_delivery_text, strip_voice_filler_prefix

    cleaned = strip_voice_filler_prefix(" ".join((spoken or "").split()).strip())
    if not cleaned:
        return cleaned
    lower = cleaned.lower()
    result = cleaned
    if kind == "news":
        if not any(
            lower.startswith(prefix)
            for prefix in (
                "señor",
                "senor",
                "aquí están",
                "aqui están",
                "las noticias",
                "en venezuela",
                "sobre ",
            )
        ):
            result = f"Señor, sobre su consulta: {cleaned}"
    elif kind == "weather":
        if not lower.startswith(("señor", "senor", "el clima")):
            result = f"Señor, el clima es el siguiente: {cleaned}"
    return finalize_voice_delivery_text(result)


def web_search_error_phrase(kind: str) -> str:
    if kind == "news":
        return (
            "Disculpe, señor. No pude obtener las noticias en este momento. "
            "¿Desea que lo intente de nuevo?"
        )
    if kind == "weather":
        return "Disculpe, señor. No pude consultar el clima ahora."
    return "Disculpe, señor. No pude consultar en internet ahora."


def split_spoken_chunks(text: str, *, max_len: int = VOICE_SPOKEN_MAX_CHARS) -> list[str]:
    """Un solo bloque — varios chunks provocan cambio de voz en Retell."""
    cleaned = fit_voice_spoken(" ".join((text or "").split()).strip(), max_chars=max_len)
    return [cleaned] if cleaned else []


def should_respond_to_transcript(
    transcript: list[Utterance],
    *,
    interaction_type: str,
) -> bool:
    """Evita autorespuestas, recordatorios vacíos y turnos parciales muy cortos."""
    user_lines = _user_lines(transcript)
    if not user_lines:
        return interaction_type == "reminder_required"

    last = user_lines[-1].strip()
    normalized = _normalize(last)
    if is_inaudible_or_noise(last):
        return False

    if normalized in _STT_ECHO_FRAGMENTS:
        return False

    if normalized in _ECHO_USER_LINES:
        return False

    if interaction_type == "reminder_required":
        return True

    if resolve_camera_voice_request(last) is not None:
        return True

    if resolve_web_search_request(last, transcript) is not None:
        return True

    if is_small_talk(last, transcript):
        return True

    if _is_concept_question(last):
        return True

    if _is_task_or_info_query(last):
        return True

    words = last.split()
    if len(words) < 2 and len(last) < 12 and not last.rstrip().endswith(("?", ".", "!")):
        return False

    return True


def _is_concept_question(text: str) -> bool:
    norm = _normalize(text)
    if len(norm) < 4:
        return False
    return bool(
        re.search(
            r"\b(qu[eé] es|qu[eé] significa|expl[ií]came|explicame|hablame de|"
            r"cu[eé]ntame qu[eé] es|dime qu[eé] es|what is|what's|explain)\b",
            norm,
        )
    )


def _is_task_or_info_query(text: str) -> bool:
    """Preguntas reales (clima, noticias, tools) — no son small talk."""
    norm = _normalize(text)
    if _is_concept_question(text):
        return True
    if _needs_internet_lookup(text):
        return True
    if bool(
        re.search(
            r"\b(publica|publicar|recuerda|memoria|carolina|imagen|genera|"
            r"video|demo|mostrar|guion|guión|relevante|estrategia|secuencia|seq|"
            r"c[aá]mara|camara|mira|visi[oó]n)\b",
            norm,
        )
    ):
        return True
    return False


def is_casual_conversation(text: str) -> bool:
    """Charla natural / personal — no requiere tools ni web."""
    if is_meta_publish_intent(text) or _is_concept_question(text):
        return False
    if is_personal_vent_intent(text):
        return True
    if (
        _needs_internet_lookup(text)
        or is_web_research_intent(text)
        or is_script_demo_request(text)
    ):
        return False
    norm = _normalize(text)
    if len(norm.split()) < 4:
        return False
    if re.search(
        r"\b(dormi|dormí|descans|descanso|cansad|cansancio|estuve|estaba|"
        r"trabaj[eé]|madrugada|despert|acabo de|reci[eé]n me levant|"
        r"sin dormir|turno|agotad|exhaust|"
        r"te decia|te decía|no habia descansado|gracias por contar|"
        r"me siento|como amanec|hoy dorm|platic|charla|"
        r"que tal tu|qué tal tu|como te fue|cómo te fue)\b",
        norm,
    ):
        return True
    return len(norm.split()) >= 9


def is_small_talk(text: str, transcript: list[Utterance] | None = None) -> bool:
    if _is_task_or_info_query(text):
        return False
    if transcript and _is_pure_ack(text):
        return False
    norm = _normalize(text)
    if norm in _SMALL_TALK or norm in _ACK_ONLY:
        return True
    if re.search(r"hola.*(como|cómo)\s+estás?\b", norm):
        return True
    if re.search(r"hola.*\bs[ií]\b", norm) and re.search(r"como\s+estas?\b", norm):
        return True
    if re.search(r"como\s+estas?\s*$", norm) or re.search(r"como\s+estas?\?", norm):
        return True
    if norm.startswith("hola") and len(norm.split()) <= 4 and len(norm) < 32:
        return True
    return False


def is_generic_agent_line(text: str) -> bool:
    norm = _normalize(text)
    if norm in {_normalize(line) for line in _GENERIC_AGENT_LINES}:
        return True
    if "operativo" in norm and "servicio" in norm:
        return True
    if norm.startswith("operativo"):
        return True
    if "en qué puedo ayudarle" in norm or "en que puedo ayudarle" in norm:
        return True
    if "sigo atento" in norm:
        return True
    if norm in {"muy bien, señor", "muy bien señor"}:
        return True
    return False

