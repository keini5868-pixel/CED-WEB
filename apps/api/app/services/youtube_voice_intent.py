"""Intenciones de YouTube por voz — reproducir, pausar, reanudar, cerrar."""

from __future__ import annotations

import re

# "pon/reproduce/busca/toca [algo] en youtube"
_PLAY_SUFFIX = re.compile(
    r"\b(?:pon(?:me|ga)?|reproduce(?:me)?|reproducir|busca(?:me|r)?|toca(?:me)?|"
    r"quiero\s+(?:ver|escuchar|o[ií]r))\s+"
    r"(?P<query>.+?)\s+"
    r"(?:en|de|desde)\s+(?:el\s+)?youtube\b",
    re.I,
)

# "en youtube pon/busca [algo]" / "busca en youtube [algo]"
_PLAY_PREFIX = re.compile(
    r"\b(?:en\s+)?youtube\s*[,:]?\s*"
    r"(?:pon(?:me|ga)?|reproduce(?:me)?|reproducir|busca(?:me|r)?|toca(?:me)?)\s+"
    r"(?P<query>.+?)\s*$"
    r"|"
    r"\b(?:pon(?:me|ga)?|reproduce(?:me)?|busca(?:me|r)?|toca(?:me)?)\s+en\s+youtube\s+"
    r"(?P<query2>.+?)\s*$",
    re.I,
)

_PAUSE = re.compile(
    r"\b(?:pausa(?:r|me)?|pon\s+(?:en\s+)?pausa|det[eé]n)\s+(?:el\s+|la\s+)?"
    r"(?:video|v[ií]deo|m[uú]sica|canci[oó]n|reproducci[oó]n|youtube)\b|"
    r"\bpausa\s+youtube\b|"
    r"\b(?:video|v[ií]deo|youtube)\s+en\s+pausa\b",
    re.I,
)

_RESUME = re.compile(
    r"\b(?:reanuda(?:r)?|contin[uú]a(?:r)?|resume|sigue(?:\s+con)?|"
    r"reproduce(?:\s+de\s+nuevo)?|dale\s+play|pon(?:le)?\s+play|quita\s+la\s+pausa)\s*"
    r"(?:(?:el|la|al)\s+)?(?:video|v[ií]deo|m[uú]sica|canci[oó]n|reproducci[oó]n|youtube)?\b",
    re.I,
)

# resume exige mención de video/música/youtube para no confundir con charla casual
_RESUME_OBJECT = re.compile(
    r"\b(video|v[ií]deo|m[uú]sica|canci[oó]n|reproducci[oó]n|youtube|play)\b", re.I
)

_CLOSE = re.compile(
    r"\b(?:cierra|cerrar|quita(?:r)?|det[eé]n|apaga(?:r)?|para(?:r)?)\s+"
    r"(?:el\s+|la\s+)?(?:panel\s+(?:de\s+)?)?"
    r"(?:youtube|reproductor(?:\s+de\s+youtube)?|video\s+de\s+youtube)\b|"
    r"\bsal(?:ir)?\s+de\s+youtube\b",
    re.I,
)

_STRIP_QUERY = re.compile(
    r"^(?:un\s+video\s+(?:de|sobre)\s+|videos?\s+(?:de|sobre)\s+|"
    r"m[uú]sica\s+de\s+|la\s+canci[oó]n\s+(?:de\s+)?|algo\s+de\s+)",
    re.I,
)
_TRAILING_FILLERS = re.compile(
    r"\s*(?:,?\s*por\s+favor|,?\s*se[nñ]or|,?\s*gracias)\s*$", re.I
)

_CONFIRM_YES = re.compile(
    r"^(?:"
    r"s[ií]|sip|sep|dale|adelante|ok|okay|vale|claro|correcto|"
    r"ese|esa|eso|el\s+primero|la\s+primera|"
    r"s[ií]\s*(?:,|\.|!)?\s*(?:ese|esa|eso|dale|por\s+favor)?"
    r")\s*[.!?]*$",
    re.I,
)
_CONFIRM_NO = re.compile(
    r"^(?:"
    r"no|nop|nel|cancel[ae]|cancela|olv[ií]dalo|mejor\s+no|"
    r"ninguno|ninguna|otro"
    r")\s*[.!?]*$",
    re.I,
)


def normalize_youtube_query(query: str) -> str:
    q = " ".join((query or "").strip().split())
    q = _TRAILING_FILLERS.sub("", q)
    q = _STRIP_QUERY.sub("", q).strip(" ¿?¡!.,:;")
    return q[:120]


def is_youtube_confirm_yes(user_text: str) -> bool:
    return bool(_CONFIRM_YES.match((user_text or "").strip()))


def is_youtube_confirm_no(user_text: str) -> bool:
    return bool(_CONFIRM_NO.match((user_text or "").strip()))


def resolve_youtube_play_request(user_text: str) -> dict[str, str] | None:
    """Devuelve {"query": ...} si el usuario pide reproducir algo en YouTube."""
    text = (user_text or "").strip()
    if not text or not re.search(r"\byoutube\b", text, re.I):
        return None
    if _CLOSE.search(text) or _PAUSE.search(text):
        return None
    m = _PLAY_SUFFIX.search(text)
    if m:
        query = normalize_youtube_query(m.group("query"))
        if query:
            return {"query": query}
    m = _PLAY_PREFIX.search(text)
    if m:
        raw = m.group("query") or m.group("query2") or ""
        query = normalize_youtube_query(raw)
        if query:
            return {"query": query}
    return None


def resolve_youtube_control(user_text: str) -> str | None:
    """Comando de control del reproductor: "pause" | "resume" | "close"."""
    text = (user_text or "").strip()
    if not text:
        return None
    if _CLOSE.search(text):
        return "close"
    if _PAUSE.search(text):
        return "pause"
    if _RESUME.search(text) and _RESUME_OBJECT.search(text):
        # "reproduce X en youtube" es play, no resume.
        if resolve_youtube_play_request(text):
            return None
        return "resume"
    return None


def is_youtube_intent(user_text: str) -> bool:
    """True si el turno es una petición o control de YouTube."""
    return bool(
        resolve_youtube_play_request(user_text)
        or resolve_youtube_control(user_text)
    )
