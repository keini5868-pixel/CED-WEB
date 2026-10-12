"""Modo grabación: CED solo habla entre «Ok CED» y «Ok CED, stop».

La llamada sigue abierta y el micrófono escucha. El resto del speech
(la presentación, el video) no genera respuesta.
"""

from __future__ import annotations

import re
import unicodedata

CUE_GREETING = "Señor, sí, dígame."

# ok / okay / okey / oye + el nombre, con los errores típicos del reconocedor.
_WAKE = re.compile(
    r"^(?:okey|okay|ok|oye)\s+(?:ced|seid|set|sec|sed|ce|c)\b\s*",
)
_STOP = re.compile(
    r"^(?:stop|alto|silencio|callate|parate|basta)(?:\s+(?:ya|ahora|por favor|ced|c))?$",
)
_FILLER = frozenset(
    {
        "",
        "si",
        "dime",
        "digame",
        "hola",
        "oye",
        "escucha",
        "por favor",
        "adelante",
    }
)


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFD", (text or "").lower())
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    folded = re.sub(r"[^a-z0-9\s]", " ", folded)
    return " ".join(folded.split())


def _tail(text: str) -> str:
    parts = (text or "").strip().split()
    if len(parts) <= 2:
        return ""
    return " ".join(parts[2:]).strip(" ,.;:¡!¿?")


def decide_cue(text: str, *, enabled: bool, listening: bool) -> tuple[str, str]:
    """off | ignore | stop | greet | answer, más el texto que debe contestar.

    ``off`` deja el turno al flujo normal. ``answer`` ya dejó a CED abierto.
    """
    raw = (text or "").strip()
    if not enabled:
        return "off", raw
    norm = _norm(raw)
    wake = _WAKE.match(norm)
    if wake:
        rest = norm[wake.end() :].strip()
        if _STOP.fullmatch(rest):
            return "stop", ""
        if rest in _FILLER:
            return "greet", ""
        question = _tail(raw)
        return ("answer", question or raw)
    if listening:
        return "answer", raw
    return "ignore", ""
