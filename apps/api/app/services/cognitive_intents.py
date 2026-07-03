"""Clasificación de intenciones — compartida voz + chat + router."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


def normalize_text(text: str) -> str:
    t = (text or "").strip().lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", t)


class CognitiveIntent(str, Enum):
    DIRECT_REPLY = "direct_reply"
    INTERNAL_KNOWLEDGE = "internal_knowledge"
    WEB_SEARCH = "web_search"
    ADVANCED_ANALYSIS = "advanced_analysis"
    MEMORY_SAVE = "memory_save"
    MEMORY_RECALL = "memory_recall"
    META_PUBLISH = "meta_publish"
    VISUAL_SEARCH = "visual_search"
    PROSPECTION = "prospection"


WEATHER_PATTERNS = [
    r"\bclima\b",
    r"\btemperatura",
    r"\bpron[oó]stico",
    r"\bqu[eé]\s+tiempo\s+hace\b",
    r"\bc[oó]mo\s+est[aá]\s+el\s+(tiempo|clima)\b",
    r"\btiempo\s+(de|en|hoy|actual)",
    r"\bllueve\b",
    r"\bgrados\b",
    r"\bweather\b",
]

NEWS_PATTERNS = [
    r"\bnoticias?\b",
    r"\búltima\s+hora\b",
    r"\bactualidad\b",
    r"\bhoy\s+en\s+",
    r"\bqu[eé]\s+pas[oó]\b",
    r"\bqu[eé]\s+pasa\s+con\b",
    r"\b[uú]ltim\w*\b.*\b(noticia|hora|titular|hoy|relevante|importante)\b",
    r"\b(noticia|titular)\w*\b.*\b[uú]ltim",
    r"\b(relevante|importante)\w*\b.*\b(noticia|mundo|internacional)\b",
    r"\b(mundo|internacional|global)\b.*\b(noticia|titular)\b",
    r"\bdime\b.*\b(noticia|ultim|titular|hoy|decir|relevante)\b",
    r"\bdame\b.*\b(noticia|ultim|titular|resumen|relevante)\b",
    r"\bbusca(r|me)?\b.*\b(noticia|titular|actualidad)\b",
    r"\bcu[eé]ntame\b.*\b(noticia|hoy|ultim)\b",
    r"\btitulares\b",
    r"\bnews\b",
    r"\blatest news\b",
    r"\bworld news\b",
]

WEB_PATTERNS = [
    r"\binvestig",
    r"\bb[uú]sca(r|me|lo|rlo)?\b",
    r"\bb[uú]scame\b",
    r"\bbusca(r|me)?\b.*\b(internet|web|google|l[ií]nea|reddit)\b",
    r"\b(informaci[oó]n|datos)\s+(sobre|de|acerca)\b",
    r"\binformaci[oó]n actualizada\b",
    r"\bdatos actuales\b",
    r"\bprecio\b.*\bhoy\b",
    r"\bc[uú]anto cuesta hoy\b",
    r"\bqu[eé]\s+es\b",
    r"\bqu[eé]\s+significa\b",
    r"\bc[uú]anto\s+(vale|cuesta|est[aá])\b",
    r"\bprecio\s+(de|del|actual)\b",
    r"\bcotizaci[oó]n\b",
    r"\bdime\b.*\b(sobre|de|precio|costo)\b",
    r"\bdame\b.*\b(precio|costo|info|informaci)\b",
    r"\bconsulta(r|me)?\b.*\b(internet|web|google|l[ií]nea)\b",
    r"\ben\s+internet\b",
    r"\bgoogle\b",
    r"\bbusca\b.*\b(en|por)\b",
    r"\b(reddit|twitter|x\.com)\b",
    r"\bmercado\b.*\bhoy\b",
    r"\btendencia\b",
]

VOLATILE_PATTERNS = [
    r"\bhoy\b",
    r"\bahora\b",
    r"\bactual(mente)?\b",
    r"\b202[4-9]\b",
    r"\b2026\b",
    r"\bprecio\b",
    r"\bcotizaci[oó]n\b",
    r"\btendencia\b",
    r"\bnoticia",
]

SCRIPT_DEMO_PATTERNS = [
    r"\bguion\b",
    r"\bgui[oó]n\b",
    r"\bscript\b",
    r"\bvideo\b",
    r"\bdemo\b",
    r"\bmostrar.*sistema\b",
    r"\bcaracter[ií]sticas.*sistema\b",
    r"\bced\b.*(video|demo|mostrar|segund)",
    r"\b\d+\s*segund",
    r"\b(veinte|veinticinco|treinta|quince|diez)\s*(y\s*)?(cinco\s*)?segund",
    r"\ban[aá]lisis avanzado\b.*\bguion\b",
    r"\bguion\b.*\b(veinte|veinticinco|25|segund)",
]

CAMERA_VOICE_PATTERNS = [
    r"\b(activa(r|me|do)?|activo|enciende|prende|abre)\s+(la\s+)?c[aá]mara\b",
    r"\b(apaga(r|me|do)?|desactiva(r|me|do)?|cierra|deja de mirar)\s+(la\s+)?c[aá]mara\b",
    r"\b(qu[eé]\s+ves|qu[eé] veo|mira esto|m[ií]rame|analiza.*(c[aá]mara|imagen|foto)|visi[oó]n)\b",
    r"\b(muestrame|mu[eé]strame|mostrar).*(c[aá]mara|pantalla|esto)\b",
    r"\b(estoy\s+)?mostrando\b",
    r"\b(lo\s+)?ves\?",
    r"\b(dime|dime qu[eé]|cu[eé]ntame qu[eé])\s+(ves|veo|observas)\b",
]

ADVANCED_PATTERNS = [
    r"\ban[aá]lisis profundo\b",
    r"\banaliza(r|me)?\s+(en detalle|a fondo|profundo)\b",
    r"\bestrategia\b",
    r"\bplan de acci[oó]n\b",
    r"\bcompar(a|ar|me)\b.*\b(opciones|alternativas)\b",
    r"\bguion\b",
    r"\bgui[oó]n\b",
    r"\bscript\b",
    r"\bperfecciona(r|me)?\b.*\b(guion|gui[oó]n|script|texto)\b",
    *SCRIPT_DEMO_PATTERNS,
]

MEMORY_SAVE_PATTERNS = [
    r"\brecuerda\b",
    r"\bguarda(r)?\s+(que|esto|en memoria)\b",
    r"\bno olvides\b",
    r"\bapunta\b",
]

MEMORY_RECALL_PATTERNS = [
    r"\bqu[eé] recuerdas\b",
    r"\bqu[eé] guardaste\b",
    r"\brecupera\b.*\bmemoria\b",
    r"\bbusca(r)?\s+en memoria\b",
]

META_PATTERNS = [
    r"\bpublica(r|me)?\b.*\b(instagram|facebook|ig|fb|redes)\b",
    r"\bpostea(r|me)?\b",
    r"\bsube(r)?\b.*\b(instagram|historia|reel)\b",
]

@dataclass
class IntentAnalysis:
    primary: CognitiveIntent
    web_kind: str  # news | weather | general
    needs_web: bool
    needs_advanced: bool
    needs_advanced_confirm: bool
    has_advanced_confirm: bool
    is_volatile: bool
    memory_save_text: str | None = None
    memory_recall_query: str | None = None


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def is_weather_intent(text: str) -> bool:
    t = normalize_text(text)
    return len(t) >= 6 and _matches(t, WEATHER_PATTERNS)


def is_news_intent(text: str) -> bool:
    t = normalize_text(text)
    return _matches(t, NEWS_PATTERNS)


def is_web_research_intent(text: str) -> bool:
    if is_news_intent(text) or is_weather_intent(text):
        return True
    t = normalize_text(text)
    if len(t) < 6:
        return False
    if re.search(r"\b(busca|buscar|buscame|investiga|google|internet|precio|cotiza)\b", t):
        return len(t) >= 6
    if len(t) < 8:
        return False
    return _matches(t, WEB_PATTERNS)


def is_internal_knowledge_query(text: str) -> bool:
    """Conceptos estables / explicaciones — cerebro interno, no web."""
    if is_news_intent(text) or is_weather_intent(text):
        return False
    t = normalize_text(text)
    if re.search(
        r"\b(busca(r|me)?\s+(en\s+)?(internet|la web|google)|"
        r"investiga(r|me)?\s+(en\s+)?(internet|la web)|"
        r"noticias?|clima|tiempo|precio|cotiza)\b",
        t,
    ):
        return False
    if re.search(
        r"\b(que es|qué es|que significa|explícame|explicame|dime que es|"
        r"cuentame que es|hablame de|informacion sobre|información sobre|"
        r"creatina|suplemento|marketing|ventas|embudo|instagram|facebook|"
        r"psicolog|psicolog\u00eda|ansiedad|estr[eé]s|depresi|emocion|mental)\b",
        t,
    ):
        return True
    if re.search(r"\b(yo\s+se|ya\s+se|se\s+lo\s+que|i know|explain|what is)\b", t):
        return True
    return False


def requires_live_web(text: str) -> bool:
    """Solo noticias/clima/datos de hoy o búsqueda explícita en internet."""
    if is_internal_knowledge_query(text):
        return False
    if is_news_intent(text) or is_weather_intent(text):
        return True
    t = normalize_text(text)
    if re.search(r"\b(precio|cuesta|cotiza|valor)\b.*\b(hoy|actual|ahora)\b", t):
        return True
    if re.search(r"\b(hoy|ahora|actual)\b.*\b(precio|cuesta|cotiza|mercado)\b", t):
        return True
    if re.search(
        r"\b(han investigado|hay investigaciones|existen estudios|otras personas|"
        r"alguien ha investigado|personas que han|quien ha investigado|"
        r"se ha estudiado|evidencia cientifica|estudios sobre|"
        r"has anyone researched|other people studied|scientific studies)\b",
        t,
    ):
        return True
    return bool(
        re.search(
            r"\b(busca(r|me)?\s+(en\s+)?(internet|la web|google|l[ií]nea)|"
            r"investiga(r|me)?\s+(en\s+(internet|la web)|sobre)|"
            r"informaci[oó]n actualizada|datos actuales|titulares|última hora)\b",
            t,
        )
    )


def is_volatile_query(text: str) -> bool:
    t = normalize_text(text)
    return _matches(t, VOLATILE_PATTERNS) or is_weather_intent(text) or is_news_intent(text)


def is_meta_publish_intent(text: str) -> bool:
    """Publicar en redes — no confundir con guion."""
    t = normalize_text(text)
    if len(t) < 6:
        return False
    return _matches(t, META_PATTERNS)


def is_advanced_request(text: str) -> bool:
    if is_meta_publish_intent(text):
        return False
    return _matches(normalize_text(text), ADVANCED_PATTERNS)


def is_script_demo_request(text: str) -> bool:
    return _matches(normalize_text(text), SCRIPT_DEMO_PATTERNS)


def is_camera_voice_command(text: str) -> bool:
    return _matches(normalize_text(text), CAMERA_VOICE_PATTERNS)


def is_explicit_advanced_activation(text: str) -> bool:
    return False


def has_advanced_confirmation(text: str) -> bool:
    return False


def is_explicit_advanced(text: str) -> bool:
    return False


def parse_memory_save(text: str) -> str | None:
    t = (text or "").strip()
    if not _matches(normalize_text(t), MEMORY_SAVE_PATTERNS):
        return None
    for pat in (
        r"recuerda\s+que\s+(.+)",
        r"guarda\s+que\s+(.+)",
        r"no olvides\s+(.+)",
        r"apunta\s+(.+)",
    ):
        m = re.search(pat, t, re.I)
        if m:
            return m.group(1).strip()[:4000]
    return t[:4000]


def analyze_intent(text: str, *, confirm_pending: bool = False) -> IntentAnalysis:
    t = normalize_text(text)
    raw = (text or "").strip()

    mem_save = parse_memory_save(raw)
    if mem_save:
        return IntentAnalysis(
            primary=CognitiveIntent.MEMORY_SAVE,
            web_kind="general",
            needs_web=False,
            needs_advanced=False,
            needs_advanced_confirm=False,
            has_advanced_confirm=False,
            is_volatile=False,
            memory_save_text=mem_save,
        )

    if _matches(t, MEMORY_RECALL_PATTERNS):
        return IntentAnalysis(
            primary=CognitiveIntent.MEMORY_RECALL,
            web_kind="general",
            needs_web=False,
            needs_advanced=False,
            needs_advanced_confirm=False,
            has_advanced_confirm=False,
            is_volatile=False,
            memory_recall_query=raw,
        )

    if _matches(t, META_PATTERNS):
        return IntentAnalysis(
            primary=CognitiveIntent.META_PUBLISH,
            web_kind="general",
            needs_web=False,
            needs_advanced=False,
            needs_advanced_confirm=False,
            has_advanced_confirm=False,
            is_volatile=False,
        )

    volatile = is_volatile_query(raw)

    prefers_web = requires_live_web(raw) or (
        is_web_research_intent(raw) and not is_internal_knowledge_query(raw)
    )
    if prefers_web:
        kind = "weather" if is_weather_intent(raw) else "news" if is_news_intent(raw) else "general"
        return IntentAnalysis(
            primary=CognitiveIntent.WEB_SEARCH,
            web_kind=kind,
            needs_web=True,
            needs_advanced=False,
            needs_advanced_confirm=False,
            has_advanced_confirm=False,
            is_volatile=True,
        )

    return IntentAnalysis(
        primary=CognitiveIntent.INTERNAL_KNOWLEDGE,
        web_kind="general",
        needs_web=False,
        needs_advanced=False,
        needs_advanced_confirm=False,
        has_advanced_confirm=False,
        is_volatile=volatile,
    )
