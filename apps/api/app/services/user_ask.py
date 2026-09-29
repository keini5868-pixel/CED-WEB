"""Qué pidió el usuario en ESTE turno — no el texto pegado alrededor.

Chat y voz deben activar módulos (finanzas, clima, memoria…) con la pregunta,
no con un guion o copy que menciona «ingresos», «hoy» o «PDF».
"""

from __future__ import annotations

import re

_ASK_MARKERS = re.compile(
    r"(?is)\b(?:"
    r"dime|decime|dec[ií]me|"
    r"qu[eé]\s+te\s+parecen|"
    r"qu[eé]\s+opinas|"
    r"c[oó]mo\s+lo\s+ves|"
    r"en\s+una\s+sola\s+frase|"
    r"opini[oó]n|"
    r"elige(?:\s+el)?|"
    r"analiza(?:\s+esto|\s+este)?|"
    r"mejor(?:a|ame)?|"
    r"corrige|"
    r"qu[eé]\s+har[ií]as|"
    r"tu\s+criterio"
    r")\b"
)

_COPY_MARKERS = re.compile(
    r"(?is)\b(?:hooks?|ganchos?|guion(?:es)?|gui[oó]n(?:es)?|copy|caption|reel|script)\b"
)

_EXPLICIT_MODULE_ASK = re.compile(
    r"(?is)\b(?:"
    r"recu[eé]rdame|"
    r"mis\s+(?:finanzas|gastos|ingresos|recordatorios)|"
    r"c[oó]mo\s+voy\s+(?:este\s+mes|con\s+mis)|"
    r"qu[eé]\s+clima|c[oó]mo\s+est[aá]\s+el\s+tiempo|"
    r"publica(?:r)?\s+(?:esto\s+)?(?:en\s+)?(?:instagram|facebook)|"
    r"busca(?:r|me)?\s+en\s+internet|"
    r"gast[eé]\s+\d|pagu[eé]\s+\d|"
    r"activa(?:r)?\s+(?:la\s+)?c[aá]mara|"
    r"genera(?:r|me)?\s+(?:una?\s+)?(?:imagen|pdf)"
    r")\b"
)


def looks_like_user_ask(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _ASK_MARKERS.search(t):
        return True
    if t.endswith("?") and len(t) <= 220:
        return True
    return False


def extract_user_ask(text: str) -> str:
    """Si hay un pegado largo, la pregunta suele ir al final."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if len(raw) < 220:
        return raw
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    last = paras[-1] if paras else raw
    if last and len(last) <= 320 and looks_like_user_ask(last):
        return last
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]
    tail = " ".join(sentences[-2:]).strip() if sentences else raw
    if tail and len(tail) <= 420 and looks_like_user_ask(tail):
        return tail
    if last and len(last) <= 200:
        return last
    return raw


def is_llm_first_turn(text: str) -> bool:
    """Opinión / copy / texto pegado + pregunta → cerebro, no módulo."""
    raw = (text or "").strip()
    if not raw:
        return False
    ask = extract_user_ask(raw)
    if _EXPLICIT_MODULE_ASK.search(ask):
        return False
    if looks_like_user_ask(ask) and (len(raw) >= 160 or ask != raw):
        return True
    if _COPY_MARKERS.search(raw) and looks_like_user_ask(ask):
        return True
    return False


def module_probe_text(text: str) -> str:
    """Texto con el que se decide si un módulo aplica."""
    raw = (text or "").strip()
    if is_llm_first_turn(raw):
        return extract_user_ask(raw)
    return raw
