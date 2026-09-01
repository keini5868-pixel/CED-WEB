"""Detección y continuación de entregables (estrategia, plan, guiones, copy) — chat, avanzado y voz."""

from __future__ import annotations

import re
from typing import Any

_DELIVERABLE_REQUEST = re.compile(
    r"\b("
    r"crea(r|me)?|hazme|haz|hacer|elabora(r|me)?|dise[nñ]a(r|me)?|escribe(r|me)?|"
    r"prepara(r|me)?|desarrolla(r|me)?|pl[aá]n|estrategia|calendario|cronograma|"
    r"semanal|mensual|lista de|paso a paso|gu[ií]a completa|roadmap|"
    r"propuesta|plan de acci[oó]n|plan de marketing|"
    r"hagamos|hag[aá]mos|armemos|montemos|ayúdame|ayudame|"
    r"dame|quiero|necesito|"
    r"guion(?:es)?|gui[oó]n(?:es)?|guio\b|caption|copy|script|"
    r"termina(?:r|lo|rlo)?|pulir|adapta(?:r|lo)?|cierra(?:lo)?|"
    r"promoci[oó]n|promocionar|lanzamiento"
    r")\b|"
    r"plan\s+para\s+(la\s+)?semana|"
    r"plan\s+para\s+(las\s+)?soluciones|"
    r"calendario\s+de\s+contenido|"
    r"estrategia\s+(de\s+)?(contenido|marketing|ventas?)|"
    r"dame\s+(una\s+)?(estrategia|plan)|"
    r"c[oó]mo\s+(?:puedo\s+)?terminarlo|"
    r"dime\s+qu[eé]\s+te\s+parece",
    re.I,
)

_STRATEGY_CONSULTATION_TOPIC = re.compile(
    r"\b("
    r"marketing|ventas?|prospecci[oó]n|contenido|redes\s+sociales|instagram|tiktok|facebook|"
    r"reels?|publicar|promoci[oó]n|embudo|leads?|clientes?|audiencia|p[uú]blico\s+ideal|"
    r"p[uú]blico\s+objetivo|copy|anuncios?|ads|engagement|seguidores|estrategia|lanzamiento|"
    r"marca|nicho|soluciones?|servicios?|negocio|emprend|"
    r"an[aá]lisis\s+de\s+contenido|qu[eé]\s+publicar|mejor\s+contenido|"
    r"guion|gui[oó]n|caption"
    r")\b",
    re.I,
)

_INTRO_ONLY_DELIVERABLE = re.compile(
    r"\b("
    r"aqu[ií] le presento|a continuaci[oó]n|te comparto|le presento|"
    r"aqu[ií] tiene|te dejo|a continuación"
    r")\b",
    re.I,
)

# Aprobación / canal / «termínalo» tras un borrador ya entregado.
_CONTINUATION_TURN = re.compile(
    r"(?is)^\s*(?:"
    r"(?:entonces\s+)?"
    r"(?:te\s+parece\s+bien|est[aá]\s+bien|me\s+parece|perfecto|vale|"
    r"ok(?:ay)?|listo|dale|vamos|s[ií]|sip|sep)|"
    r"(?:es\s+)?(?:para|en|por)\s+"
    r"(?:instagram|instagr[ae]m|imtagr[ae]n|facebook|face\b|fb\b|tiktok|"
    r"reels?|stories|redes(?:\s+sociales)?|youtube|landing|el\s+sitio)|"
    r"(?:lo\s+)?(?:voy\s+a\s+)?public(?:ar|o)\s+(?:en|por)|"
    r"publ[ií]calo|s[uú]belo|"
    r"term[ií]na(?:lo|rlo)?|cierra(?:lo)?|pul[ií]rlo|ad[aá]ptalo|"
    r"versi[oó]n\s+(?:corta|final|para\s+redes)|"
    r"c[oó]mo\s+(?:puedo\s+)?terminarlo|"
    r"deja(?:lo)?\s+as[ií]|as[ií]\s+est[aá]\s+bien"
    r")\b",
)

_PRIOR_LOOKS_LIKE_DELIVERABLE = re.compile(
    r"(?is)(?:"
    r"\bnaci[oó]\s+\*?\*?ced\b|"
    r"\bguion\b|\bgui[oó]n\b|\bcaption\b|\bcopy\b|"
    r"\bcall to action\b|\bcta\b|"
    r"\bpor qu[eé] funciona\b|"
    r"\bsi no lo intento\b|"
    r"\bno soy\b.{0,40}\b(?:gemini|openai|anthropic|claude)\b|"
    r"(?:^|\n)\s*(?:#{1,3}\s|\d+[\.)]\s|[-*]\s+)"
    r")",
)

DELIVERABLE_CONTINUATION_MESSAGE = (
    "Tu respuesta anterior quedó INCOMPLETA: solo escribiste la introducción "
    "y no entregaste el contenido que pedí. "
    "Usa el contexto que ya compartí en la conversación (público, soluciones, negocio). "
    "Continúa AHORA con el entregable COMPLETO (estrategia, plan, lista, guion o copy). "
    "No repitas la introducción. Incluye público objetivo y detalle accionable "
    "(por ejemplo Lunes–Domingo si es semanal)."
)

VOICE_DELIVERABLE_CONTINUATION_OVERLAY = (
    "Tu respuesta anterior quedó INCOMPLETA: solo diste la introducción sin el contenido pedido. "
    "Continúa AHORA con el entregable COMPLETO para voz (estrategia, plan, guion o lista). "
    "No repitas la introducción. Incluye público objetivo y acciones concretas "
    "(por ejemplo Lunes a Domingo si es semanal). "
    "Usa oraciones completas, secciones numeradas breves, sin asteriscos ni markdown."
)

VOICE_DELIVERABLE_OVERLAY = """
# ENTREGA COMPLETA (estrategia / plan / lista / guión / copy)
El usuario pidió CREAR, TERMINAR o ADAPTAR un entregable concreto.
Usa público, soluciones y canales que YA mencionó — no repitas preguntas innecesarias.
PROHIBIDO quedarse solo en la introducción («Aquí le presento…») sin el contenido real.
PROHIBIDO re-emitir tu respuesta anterior completa y luego empezar otra versión.
Una sola versión limpia y completa. Oraciones cerradas (no cortes a media frase).
Para voz: oraciones completas, secciones numeradas breves (1, 2, 3), sin asteriscos ni markdown.
No preguntes si quiere continuar — entrégalo completo en esta respuesta.
""".strip()

DELIVERABLE_FINISH_OVERLAY = """
# CIERRE DE ENTREGABLE (OBLIGATORIO ESTE TURNO)
El usuario YA tiene un borrador en el historial y ahora aprueba, pide terminar,
o indica el canal (Instagram, Facebook, TikTok, redes, etc.).

OBLIGATORIO:
1) Entrega YA la versión FINAL lista para usar (caption / guion corto / post).
2) Adapta al canal si lo dijo (IG+FB = texto corto, emocional, 1 CTA claro).
3) UNA sola versión limpia. PROHIBIDO pegar dos borradores seguidos.
4) PROHIBIDO re-emitir tu respuesta anterior completa y luego reescribirla.
5) PROHIBIDO preguntar otra vez «¿video, landing o redes?» si ya dijo el canal.
6) PROHIBIDO cortar a media frase. Cierra con punto y CTA.
7) No metas FitLine/PM ni catálogo de módulos salvo que el usuario lo pida en ESTE guion.
""".strip()

CHAT_DELIVERABLE_RULES = """
IMPORTANTE — ENTREGAS COMPLETAS (estrategia, plan, análisis, listas, guiones, ideas, copy, prompts):
- Si el usuario pide CREAR, TERMINAR o ADAPTAR algo (idea, copy, prompt, guion, caption), entrégalo COMPLETO en el mismo mensaje.
- Si aprueba («te parece bien», «ok») o elige canal («para Instagram/Facebook»), cierra con la versión final YA — sin más cuestionario de medio.
- Usa contexto previo del chat — NO repitas preguntas ya respondidas.
- PROHIBIDO quedarse solo en la introducción («Aquí le presento…», «A continuación…») sin el contenido real.
- PROHIBIDO re-emitir el borrador anterior completo y luego otra versión a medias (duplicado + corte).
- Una sola versión final, oraciones cerradas, CTA claro.
- Para plan o estrategia semanal: incluye público objetivo + calendario día a día (Lunes–Domingo).
- Idea/copy/prompt de texto ≠ imagen: no generes imagen salvo pedido visual explícito.

IMPORTANTE — charla natural y cambio de tema:
- Si el usuario cambia de tema («cambiando el tema», charla personal, salud, cansancio, desahogo), NO sigas en modo estrategia ni marketing.
- Responde con empatía breve y natural; NO generes imágenes, PDFs ni planes salvo que lo pidan explícitamente en ese mensaje.
- El historial de estrategia es contexto opcional, no un modo permanente.
""".strip()


def is_strategy_consultation_topic(text: str) -> bool:
    """Tema de marketing/ventas/contenido — activa rol consultor (descubrimiento o entrega)."""
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) < 8:
        return False
    return bool(_STRATEGY_CONSULTATION_TOPIC.search(cleaned))


def is_deliverable_request(text: str) -> bool:
    return bool(_DELIVERABLE_REQUEST.search(text or ""))


def _history_rows(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [h for h in (history or []) if isinstance(h, dict)]


def last_assistant_deliverable_text(
    history: list[dict[str, Any]] | None,
    *,
    min_len: int = 120,
) -> str:
    for msg in reversed(_history_rows(history)):
        role = str(msg.get("role") or "").lower()
        if role not in ("assistant", "model", "claude"):
            continue
        prev = str(msg.get("content") or "").strip()
        if len(prev) < min_len:
            continue
        if _PRIOR_LOOKS_LIKE_DELIVERABLE.search(prev) or has_deliverable_structure(prev):
            return prev
        if len(prev) >= 280:
            return prev
    return ""


def is_deliverable_continuation_turn(
    user_text: str,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    """True si el usuario aprueba/pide canal/cierre tras un borrador ya entregado."""
    t = " ".join((user_text or "").split()).strip()
    if len(t) < 2:
        return False
    channel_pick = bool(
        re.search(
            r"(?i)\b(?:instagram|instagr[ae]m|imtagr[ae]n?|facebook|face\b|fb\b|"
            r"tiktok|reels?|redes(?:\s+sociales)?)\b",
            t,
        )
    )
    approval = bool(_CONTINUATION_TURN.search(t))
    if not approval and not channel_pick:
        return False
    prior = last_assistant_deliverable_text(history)
    if prior:
        return True
    # Sin historial disponible: aún así subir presupuesto / overlay de cierre
    # (evita cortar a 280 tokens en «te parece bien» / «para Instagram»).
    if re.search(
        r"(?i)\b(?:termina(?:lo|rlo)?|ad[aá]ptalo|versi[oó]n\s+final|"
        r"c[oó]mo\s+(?:puedo\s+)?terminarlo)\b",
        t,
    ):
        return True
    if channel_pick:
        return True
    if approval and len(t) <= 140:
        return True
    return False


def needs_deliverable_token_budget(
    user_text: str,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    return is_deliverable_request(user_text) or is_deliverable_continuation_turn(
        user_text, history
    )


def append_deliverable_finish_if_needed(
    system: str,
    user_text: str,
    history: list[dict[str, Any]] | None = None,
) -> str:
    if not is_deliverable_continuation_turn(user_text, history):
        return system
    base = (system or "").rstrip()
    if "CIERRE DE ENTREGABLE" in base:
        return base
    return f"{base}\n\n{DELIVERABLE_FINISH_OVERLAY}" if base else DELIVERABLE_FINISH_OVERLAY


def has_deliverable_structure(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if re.search(
        r"(?m)^\s*(#{1,3}\s|\d+[\.)]\s|[-*]\s+|"
        r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b)",
        cleaned,
        re.I,
    ):
        return True
    return cleaned.count("\n") >= 4 and len(cleaned) >= 400


def is_intro_only_deliverable(text: str) -> bool:
    cleaned = (text or "").strip()
    return bool(
        _INTRO_ONLY_DELIVERABLE.search(cleaned) and not has_deliverable_structure(cleaned)
    )


def looks_truncated_mid_sentence(text: str) -> bool:
    cleaned = (text or "").rstrip()
    if len(cleaned) < 40:
        return False
    if cleaned.endswith(("...", "…")):
        return True
    if cleaned[-1] in ".!?…»\"'”)" and not cleaned.endswith(","):
        return False
    # Corta en palabra / conector típico
    if re.search(
        r"(?i)(?:\b(?:que|de|y|con|para|en|el|la|un|una|su|tu|mi|habla|habl[eé])|"
        r"[,:;]|—|-)\s*$",
        cleaned,
    ):
        return True
    return cleaned[-1].isalnum()


def is_incomplete_deliverable(
    reply: str,
    user_text: str,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    cleaned = (reply or "").strip()
    if looks_truncated_mid_sentence(cleaned):
        return True
    cont = is_deliverable_continuation_turn(user_text, history)
    if cont and len(cleaned) < 180:
        return True
    if not is_deliverable_request(user_text) and not cont:
        return False
    if len(cleaned) < 120:
        return True
    if has_deliverable_structure(cleaned):
        weekday_hits = len(
            re.findall(
                r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b",
                cleaned,
                re.I,
            )
        )
        if weekday_hits >= 3 and len(cleaned) >= 200:
            return False
        if len(cleaned) >= 280 and not looks_truncated_mid_sentence(cleaned):
            return False
    if is_intro_only_deliverable(cleaned):
        return True
    if re.search(r"\b(dirigida? a un p[uú]blico|para un p[uú]blico)\s*$", cleaned, re.I):
        return True
    return len(cleaned) < 420


def _normalize_passage(text: str) -> str:
    t = re.sub(r"[^\w\s]", "", (text or "").lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def collapse_repeated_deliverable_passages(text: str) -> str:
    """Quita párrafos / aperturas duplicadas (dos borradores apilados)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned

    parts = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    if len(parts) >= 2:
        out: list[str] = []
        for part in parts:
            pn = _normalize_passage(part)
            if not pn:
                continue
            drop = False
            for i, prev in enumerate(out):
                prev_n = _normalize_passage(prev)
                if not prev_n:
                    continue
                same_open = (
                    len(pn) >= 40
                    and len(prev_n) >= 40
                    and (pn[:55] == prev_n[:55] or pn in prev_n or prev_n in pn)
                )
                if pn == prev_n or same_open:
                    if len(pn) > len(prev_n):
                        out[i] = part
                    drop = True
                    break
            if not drop:
                out.append(part)
        cleaned = "\n\n".join(out)

    # Frase firma repetida (ej. «si no lo intento…») → dejar solo la primera aparición completa
    sig = re.compile(
        r"(?is)((?:pero\s+)?un\s+d[ií]a\s+tuve\s+una\s+idea.{0,120}?"
        r"si\s+no\s+lo\s+intento.{0,80}?lograrlo\.?)"
    )
    matches = list(sig.finditer(cleaned))
    if len(matches) >= 2:
        # Conservar desde el último bloque coherente si el primero es basura corta
        first_end = matches[0].end()
        second_start = matches[1].start()
        # Si hay mucho texto basura entre duplicados, quedarse con el tramo tras el 1.er corte
        # Mejor: eliminar el segundo match y lo que lo precede si es eco corto
        before_second = cleaned[:second_start].rstrip()
        after_second = cleaned[matches[1].start() :]
        if len(before_second) < len(after_second) * 0.85:
            cleaned = after_second.strip()
        else:
            cleaned = (before_second + cleaned[matches[1].end() :]).strip()

    half = len(cleaned) // 2
    if half > 120:
        first = cleaned[:half].strip()
        second = cleaned[half:].strip()
        if _normalize_passage(first)[:80] == _normalize_passage(second)[:80]:
            cleaned = second if len(second) >= len(first) else first

    return cleaned.strip()


def merge_deliverable_continuation(original: str, continuation: str) -> str:
    """Une respuesta truncada con continuación (chat o voz).

    Si la continuación es una versión alternativa completa (no un remate),
    se queda SOLO con una — nunca apila dos respuestas.
    """
    base = (original or "").strip()
    extra = (continuation or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    if is_intro_only_deliverable(base):
        return collapse_repeated_deliverable_passages(extra) if extra else base
    if looks_truncated_mid_sentence(base) and len(extra) >= 40:
        # Preferir continuación limpia si el base está cortado
        if len(extra) >= max(80, int(len(base) * 0.5)):
            return collapse_repeated_deliverable_passages(extra)
        return collapse_repeated_deliverable_passages(
            f"{base.rstrip()}\n\n{extra}".strip()
        )

    # Continuación que reinicia el discurso = variante apilada → quedarse con una.
    extra_l = extra.lower()
    if re.match(
        r"^(?:mire|claro|perfecto|bueno|hola|bien|entendido|por supuesto|se[nñ]or)\b",
        extra_l,
    ) and len(extra) >= max(80, int(len(base) * 0.45)):
        chosen = extra if len(extra) >= len(base) * 0.6 else base
        return collapse_repeated_deliverable_passages(chosen)

    a = _normalize_passage(base[:160])
    b = _normalize_passage(extra[:160])
    if a and b and (a[:36] == b[:36] or a in b or b in a):
        chosen = extra if len(extra) >= len(base) else base
        return collapse_repeated_deliverable_passages(chosen)

    return collapse_repeated_deliverable_passages(
        f"{base.rstrip()}\n\n{extra}".strip()
    )
