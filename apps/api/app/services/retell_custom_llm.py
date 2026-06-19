"""Utilidades del protocolo Retell Custom LLM."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.services.cognitive_intents import (
    has_advanced_confirmation,
    is_advanced_request,
    is_camera_voice_command,
    is_explicit_advanced,
    is_explicit_advanced_activation,
    is_internal_knowledge_query,
    is_meta_publish_intent,
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
    if _needs_internet_lookup(last) and not _FRAGMENT_PREFIX.search(ln):
        if is_news_intent(last) or is_weather_intent(last) or is_web_research_intent(last):
            return False
    if len(ln.split()) <= 4 and _FRAGMENT_PREFIX.search(ln):
        return True
    if len(ln.split()) <= 2 and _needs_internet_lookup(pn):
        return True
    return False


def _needs_internet_lookup(text: str) -> bool:
    if is_internal_knowledge_query(text):
        return False
    if is_weather_intent(text) or is_news_intent(text):
        return True
    if requires_live_web(text):
        return True
    norm = normalize_text(text)
    if len(norm) < 4 or norm in _ACK_ONLY:
        return False
    if is_volatile_query(text) and _WEB_FRAGMENT_HINTS.search(norm):
        return is_news_intent(text) or is_weather_intent(text)
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


def resolve_meta_publish_request(user_text: str) -> dict[str, str] | None:
    """Publicación directa en Meta — prioridad sobre sistema avanzado."""
    last = (user_text or "").strip()
    if not last or not is_meta_publish_intent(last):
        return None
    norm = _normalize(last)
    platform = "instagram" if re.search(r"\b(instagram|ig)\b", norm) else "facebook"
    caption = ""
    for pat in (
        r"\bpublica(?:r|me|lo|que|ar)?\s+(?:en\s+)?(?:instagram|ig|facebook|fb)\b[\s,:-]*(.+)$",
        r"\bpublique\s+(?:esa\s+imagen\s+)?(?:en\s+)?(?:instagram|ig)\b[\s,:-]*(.+)$",
        r"\b(?:sube|postea)(?:r|me|lo)?\s+(?:en\s+)?(?:instagram|ig|facebook|fb)\b[\s,:-]*(.+)$",
    ):
        m = re.search(pat, last, re.I)
        if m and m.group(1):
            caption = m.group(1).strip(" .,:;-")
            break
    return {"platform": platform, "caption": caption}


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
    if has_advanced_confirmation(last) and len(_normalize(last).split()) <= 2:
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


def fallback_advanced_topic(
    transcript: list[Utterance],
    *,
    pending_topic: str | None = None,
) -> str:
    if pending_topic:
        return pending_topic
    for line in reversed(_user_lines(transcript)):
        cleaned = line.strip()
        if not cleaned or _is_pure_ack(cleaned):
            continue
        if is_script_demo_request(cleaned) or is_advanced_request(cleaned):
            return cleaned
        norm = _normalize(cleaned)
        if len(norm.split()) >= 5:
            return cleaned
    return DEFAULT_SCRIPT_TOPIC


def advanced_analysis_hold_phrase() -> str:
    return "Activo el sistema avanzado, señor. Un momento."


_AGENT_ADVANCED_CONFIRM = re.compile(
    r"sistema avanzado|an[aá]lisis avanzado|an[aá]lisis profundo|"
    r"modo avanzado|confirma|desea que|perfeccion|generar el guion|generar el gui[oó]n",
    re.I,
)


def agent_asked_advanced_confirm(transcript: list[Utterance]) -> bool:
    for utterance in transcript:
        if utterance.role == "user":
            continue
        content = (utterance.content or "").strip()
        if content and _AGENT_ADVANCED_CONFIRM.search(content):
            return True
    return False


def _substantive_user_lines(transcript: list[Utterance]) -> list[str]:
    lines: list[str] = []
    for line in _user_lines(transcript):
        cleaned = line.strip()
        if not cleaned or _is_pure_ack(cleaned):
            continue
        if has_advanced_confirmation(cleaned) and not (
            is_script_demo_request(cleaned)
            or is_explicit_advanced_activation(cleaned)
            or len(_normalize(cleaned).split()) >= 5
        ):
            continue
        lines.append(cleaned)
    return lines


def should_execute_advanced_now(user_text: str, topic: str) -> bool:
    """Ejecuta Claude solo para guiones/demos o tras confirmación explícita."""
    if is_camera_voice_command(user_text):
        return False
    if is_meta_publish_intent(user_text) or is_meta_publish_intent(topic):
        return False
    if is_script_demo_request(topic) or is_script_demo_request(user_text):
        return True
    if has_advanced_confirmation(user_text) or is_explicit_advanced_activation(user_text):
        if is_meta_publish_intent(topic):
            return False
        return True
    if is_explicit_advanced(user_text):
        return True
    return False


def resolve_advanced_analysis_request(
    user_text: str,
    transcript: list[Utterance],
    *,
    pending_topic: str | None = None,
) -> str | None:
    """Detecta confirmación de sistema avanzado o petición directa de guion/análisis."""
    last = (user_text or "").strip()
    if not last:
        return pending_topic

    if is_camera_voice_command(last):
        return None

    if is_meta_publish_intent(last):
        return None

    if is_explicit_advanced_activation(last):
        return fallback_advanced_topic(transcript, pending_topic=pending_topic)

    if is_script_demo_request(last) and not _is_pure_ack(last):
        return last
    if is_explicit_advanced(last):
        return last

    if has_advanced_confirmation(last) or is_explicit_advanced_activation(last) or _is_pure_ack(last):
        if transcript_has_meta_publish_context(transcript):
            return None
        if pending_topic:
            return pending_topic

        seen_agent_confirm = False
        for utterance in reversed(transcript):
            content = (utterance.content or "").strip()
            if not content:
                continue
            role = utterance.role
            if role != "user":
                if seen_agent_confirm:
                    continue
                if _AGENT_ADVANCED_CONFIRM.search(content):
                    seen_agent_confirm = True
            elif seen_agent_confirm:
                if _is_pure_ack(content):
                    continue
                return content

        substantive = _substantive_user_lines(transcript)
        if substantive:
            return substantive[-1]

        if has_advanced_confirmation(last) or is_explicit_advanced_activation(last):
            return fallback_advanced_topic(transcript, pending_topic=pending_topic)

    return None


def is_unwanted_voice_reply(text: str, *, user_text: str = "") -> bool:
    """Detecta relleno tipo chatbot o re-preguntas de confirmación."""
    if is_generic_agent_line(text):
        return True
    norm = _normalize(text)
    if re.search(r"activo an[aá]lisis avanzado|sistema avanzado.*\?", norm):
        return True
    if re.search(r"sigo atento|continuamos|en qu[eé] m[aá]s puedo", norm):
        return True
    if user_text and (
        has_advanced_confirmation(user_text) or is_explicit_advanced_activation(user_text)
    ):
        if "en qué puedo ayudarle" in norm or "en que puedo ayudarle" in norm:
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
    if has_advanced_confirmation(last) or is_explicit_advanced_activation(last):
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
    """Parte respuestas largas de guion en dos bloques secuenciales (sin solaparse)."""
    from app.services.voice_spoken import is_advisory_voice_query, voice_spoken_limit

    limit = voice_spoken_limit(topic)
    cleaned = fit_voice_spoken(" ".join((text or "").split()).strip(), max_chars=limit)
    if not cleaned:
        return []
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
        return "Un momento, señor. Consulto el clima y vuelvo con el resultado."
    if kind == "news":
        return "Un momento, señor. Consulto las noticias más relevantes del día."
    return "Un momento, señor."


def format_web_delivery(kind: str, spoken: str) -> str:
    cleaned = " ".join((spoken or "").split()).strip()
    if not cleaned:
        return cleaned
    lower = cleaned.lower()
    if kind == "news":
        if any(
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
            return cleaned
        return f"Señor, sobre su consulta: {cleaned}"
    if kind == "weather":
        if lower.startswith(("señor", "senor", "el clima")):
            return cleaned
        return f"Señor, el clima es el siguiente: {cleaned}"
    return cleaned


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

    if has_advanced_confirmation(last) or is_explicit_advanced_activation(last):
        return True

    if resolve_camera_voice_request(last) is not None:
        return True

    if resolve_web_search_request(last, transcript) is not None:
        return True

    if resolve_advanced_analysis_request(last, transcript) is not None:
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
            r"cu[eé]ntame qu[eé] es|dime qu[eé] es)\b",
            norm,
        )
    )


def _is_task_or_info_query(text: str) -> bool:
    """Preguntas reales (clima, noticias, tools, estrategia) — no son small talk."""
    norm = _normalize(text)
    if _is_concept_question(text):
        return True
    if _needs_internet_lookup(text):
        return True
    if is_casual_conversation(text):
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
    if len(norm.split()) >= 8:
        return True
    return False


def is_casual_conversation(text: str) -> bool:
    """Charla natural / personal — no requiere tools ni web."""
    if is_meta_publish_intent(text) or _is_concept_question(text):
        return False
    if _needs_internet_lookup(text) or is_script_demo_request(text):
        return False
    norm = _normalize(text)
    if len(norm.split()) < 4:
        return False
    if re.search(
        r"\b(dormi|dormí|descans|descanso|cansad|cansancio|estuve|estaba|"
        r"te decia|te decía|no habia descansado|gracias por contar|"
        r"me siento|como amanec|hoy dorm|platic|charla)\b",
        norm,
    ):
        return True
    return len(norm.split()) >= 9


def casual_conversation_reply(text: str) -> str:
    norm = _normalize(text)
    if re.search(r"\b(dormi|dormí|descans)\b", norm):
        return "Qué bueno, señor. Descansar lo necesario es clave. ¿Se siente mejor ahora?"
    if re.search(r"\b(cansad|cansancio|agotad|estres)\b", norm):
        return "Lo comprendo, señor. Cuídese; el descanso forma parte del rendimiento."
    if re.search(r"\b(te decia|te decía|estuve|estaba)\b", norm):
        return "Entendido, señor. Gracias por contármelo. ¿Seguimos con algo en lo que pueda ayudarle?"
    return "Entendido, señor. Gracias por compartirlo conmigo."


def is_small_talk(text: str, transcript: list[Utterance] | None = None) -> bool:
    if _is_task_or_info_query(text):
        return False
    if is_explicit_advanced_activation(text):
        return False
    if transcript and resolve_advanced_analysis_request(text, transcript) is not None:
        return False
    if transcript and (
        has_advanced_confirmation(text)
        or _is_pure_ack(text)
        or is_explicit_advanced_activation(text)
    ):
        return False
    norm = _normalize(text)
    if norm in _SMALL_TALK or norm in _ACK_ONLY:
        return True
    if re.search(r"hola.*(como|cómo)\s+estás?\b", norm):
        return True
    if re.search(r"hola.*\bs[ií]\b", norm) and re.search(r"(como|cómo)\s+estás?\b", norm):
        return True
    if re.search(r"(como|cómo)\s+estás?\s*$", norm) or re.search(r"(como|cómo)\s+estás?\?", norm):
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
    if re.search(r"activo an[aá]lisis avanzado", norm):
        return True
    if norm in {"muy bien, señor", "muy bien señor"}:
        return True
    return False


def concise_reply_for_small_talk(
    user_text: str,
    transcript: list[Utterance] | None = None,
) -> str:
    norm = _normalize(user_text)
    user_lines = _user_lines(transcript or [])

    if re.search(r"(como|cómo)\s+estás?\b", norm) or "qué tal" in norm or "que tal" in norm:
        return "Muy bien, señor. ¿En qué puedo ayudarle?"
    if norm.startswith("hola") or norm in ("buenos días", "buenas tardes", "buenas noches"):
        return "Buenos días, señor. ¿En qué puedo ayudarle?"
    if norm in _ACK_ONLY and len(user_lines) <= 1:
        return "¿En qué puedo ayudarle, señor?"
    return "¿En qué puedo ayudarle, señor?"
