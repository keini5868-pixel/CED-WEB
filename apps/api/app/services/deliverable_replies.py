"""Detección y continuación de entregables (estrategia, plan, listas) — chat y voz."""

from __future__ import annotations

import re

_DELIVERABLE_REQUEST = re.compile(
    r"\b("
    r"crea(r|me)?|hazme|haz|elabora(r|me)?|dise[nñ]a(r|me)?|escribe(r|me)?|"
    r"prepara(r|me)?|desarrolla(r|me)?|pl[aá]n|estrategia|calendario|cronograma|"
    r"semanal|mensual|lista de|paso a paso|gu[ií]a completa|roadmap|"
    r"propuesta|plan de acci[oó]n|plan de marketing|"
    r"hagamos|hag[aá]mos|armemos|montemos|"
    r"dame|quiero|necesito|"
    r"promoci[oó]n|promocionar|lanzamiento"
    r")\b|"
    r"plan\s+para\s+(la\s+)?semana|"
    r"plan\s+para\s+(las\s+)?soluciones|"
    r"calendario\s+de\s+contenido|"
    r"estrategia\s+(de\s+)?(contenido|marketing|ventas?)|"
    r"dame\s+(una\s+)?(estrategia|plan)",
    re.I,
)

_STRATEGY_CONSULTATION_TOPIC = re.compile(
    r"\b("
    r"marketing|ventas?|prospecci[oó]n|contenido|redes\s+sociales|instagram|tiktok|facebook|"
    r"reels?|publicar|promoci[oó]n|embudo|leads?|clientes?|audiencia|p[uú]blico\s+ideal|"
    r"p[uú]blico\s+objetivo|copy|anuncios?|ads|engagement|seguidores|estrategia|lanzamiento|"
    r"marca|nicho|soluciones?|servicios?|negocio|emprend|"
    r"an[aá]lisis\s+de\s+contenido|qu[eé]\s+publicar|mejor\s+contenido"
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

DELIVERABLE_CONTINUATION_MESSAGE = (
    "Tu respuesta anterior quedó INCOMPLETA: solo escribiste la introducción "
    "y no entregaste el contenido que pedí. "
    "Usa el contexto que ya compartí en la conversación (público, soluciones, negocio). "
    "Continúa AHORA con el entregable COMPLETO (estrategia, plan, lista o análisis). "
    "No repitas la introducción. Incluye público objetivo y detalle accionable "
    "(por ejemplo Lunes–Domingo si es semanal)."
)

VOICE_DELIVERABLE_CONTINUATION_OVERLAY = (
    "Tu respuesta anterior quedó INCOMPLETA: solo diste la introducción sin el contenido pedido. "
    "Continúa AHORA con el entregable COMPLETO para voz (estrategia, plan o lista). "
    "No repitas la introducción. Incluye público objetivo y acciones concretas "
    "(por ejemplo Lunes a Domingo si es semanal). "
    "Usa oraciones completas, secciones numeradas breves, sin asteriscos ni markdown."
)

VOICE_DELIVERABLE_OVERLAY = """
# ENTREGA COMPLETA (estrategia / plan / lista / guión)
El usuario pidió CREAR o ELABORAR un entregable concreto (plan, estrategia, calendario).
Usa público, soluciones y canales que YA mencionó en la conversación — no repitas preguntas innecesarias.
PROHIBIDO quedarse solo en la introducción («Aquí le presento…») sin el contenido real.
Para plan o estrategia semanal: incluye público objetivo + calendario Lunes a Domingo con acciones concretas
ligadas a sus soluciones y redes.
Para voz: oraciones completas, secciones numeradas breves (1, 2, 3), sin asteriscos ni markdown.
No preguntes si quiere continuar — entrégalo completo en esta respuesta.
Cierra cada idea en oración completa para que suene natural al hablar.
""".strip()

CHAT_DELIVERABLE_RULES = """
IMPORTANTE — ENTREGAS COMPLETAS (estrategia, plan, análisis, listas, guiones, ideas, copy, prompts):
- Si el usuario pide CREAR o ELABORAR algo (incluida idea, copy, prompt o contenido de texto), entrégalo COMPLETO en el mismo mensaje.
- Usa contexto previo del chat (público, soluciones, negocio) — NO repitas preguntas ya respondidas.
- PROHIBIDO quedarse solo en la introducción («Aquí le presento…», «A continuación…») sin el contenido real.
- Para plan o estrategia semanal: incluye público objetivo + calendario día a día (Lunes–Domingo) con acciones concretas por solución/canal.
- No preguntes «¿quieres que continúe?» si ya pidieron el entregable — entrégalo de una vez.
- Usa markdown con títulos, listas numeradas o días de la semana para que sea fácil de leer y copiar.
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


def is_incomplete_deliverable(reply: str, user_text: str) -> bool:
    if not is_deliverable_request(user_text):
        return False
    cleaned = (reply or "").strip()
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
        if len(cleaned) >= 280:
            return False
    if is_intro_only_deliverable(cleaned):
        return True
    if re.search(r"\b(dirigida? a un p[uú]blico|para un p[uú]blico)\s*$", cleaned, re.I):
        return True
    return len(cleaned) < 420


def merge_deliverable_continuation(original: str, continuation: str) -> str:
    """Une respuesta truncada con continuación (chat o voz)."""
    base = (original or "").strip()
    extra = (continuation or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    if is_intro_only_deliverable(base):
        return extra
    return f"{base.rstrip()}\n\n{extra}".strip()
