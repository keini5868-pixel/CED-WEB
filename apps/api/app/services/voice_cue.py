"""Stop de presentación y despertar con «Ok CED» (independiente del micrófono).

Tras «stop», CED calla hasta el siguiente aviso. «Ok CED» / variantes STT
lo reactivan; otro «stop» lo vuelve a callar.
"""

from __future__ import annotations

import re
import unicodedata

CUE_GREETING = "Señor, sí, dígame."

_WAKE_LEAD = frozenset(
    {
        "ok",
        "okay",
        "okey",
        "okei",
        "okai",
        "oquei",
        "okaye",
        "oye",
        "hey",
        "ey",
        "oi",
        "oki",
    }
)
# CED / SET y lo que el reconocedor suele escribir en su lugar.
_NAME_EXACT = frozenset(
    {
        "ced",
        "set",
        "sec",
        "sed",
        "seid",
        "said",
        "sit",
        "cet",
        "zed",
        "zet",
        "sede",
        "cede",
        "seed",
        "sid",
        "cid",
        "ce",
        "se",
        "c",
        "see",
        "ched",
        "ked",
        "ted",
        "sett",
        "sep",
        "cep",
        "seth",
        "seht",
        "jed",
        "cedd",
        "sedd",
        "cedo",
        "seto",
    }
)
_STOP_WORD = frozenset(
    {
        "stop",
        "stopo",
        "stopa",
        "stoppo",
        "estop",
        "estopo",
        "istop",
        "etop",
        "eetop",
        "top",
        "stopp",
        "sstop",
        "stap",
        "stpo",
        "alto",
        "silencio",
        "callate",
        "calla",
        "cayate",
        "parate",
        "basta",
        "detente",
        "deten",
        "quieto",
        "para",
        "parar",
        "detener",
        "cancela",
        "cancelar",
    }
)
# stop / estop + vocal que el micrófono pega: stopo, estopo, stoppo.
_STOP_SHAPE = re.compile(r"^(e+)?s+t+o+p+[aeiou]*$")
_STOP_ECHO = frozenset({"o", "oh", "a", "ah", "e", "eh", "p", "u"})
_GLUE = frozenset(
    {
        "si",
        "dime",
        "digame",
        "hola",
        "oye",
        "escucha",
        "por",
        "favor",
        "adelante",
        "ya",
        "ahora",
        "entonces",
        "y",
        "e",
        "un",
        "el",
        "la",
        "me",
        "please",
        "and",
        "then",
        "ahi",
    }
)
_ADDRESS = frozenset({"senor", "senora", "don", "dona"})
_FILLER = frozenset(
    {
        "",
        "si",
        "sí",
        "ok",
        "okay",
        "okey",
        "dime",
        "digame",
        "hola",
        "hola si",
        "hola sí",
        "oye",
        "escucha",
        "por favor",
        "adelante",
        "listo",
        "bueno",
    }
)
# «estop» suele llegar como «esto», «es todo» o «es top». Solo la frase corta.
_SHORT_STOP = frozenset(
    {
        "esto",
        "esta",
        "estoy",
        "es todo",
        "es top",
        "es stop",
        "e stop",
        "e top",
        "est op",
        "esstop",
        "s top",
        "es to",
        "esto p",
        "el esto",
        "un esto",
    }
)


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFD", (text or "").lower())
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    folded = re.sub(r"[^a-z0-9\s]", " ", folded)
    return " ".join(folded.split())


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 1:
        return 2
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(
                    prev[j] + 1,
                    cur[-1] + 1,
                    prev[j - 1] + (ca != cb),
                )
            )
        prev = cur
    return prev[-1]


def mentions_ced_name(text: str) -> bool:
    """True si la frase nombra a CED, aunque el micrófono escriba SET/SEC."""
    return any(_is_name(token) for token in _norm(text).split())


def _is_name(token: str) -> bool:
    if token in _NAME_EXACT:
        return True
    if not 2 <= len(token) <= 5:
        return False
    return any(_edit_distance(token, base) <= 1 for base in ("ced", "set", "sec", "sed"))


def _is_stop_word(token: str) -> bool:
    if token in _STOP_WORD:
        return True
    if _STOP_SHAPE.match(token):
        return True
    if 3 <= len(token) <= 6 and _edit_distance(token, "stop") <= 1:
        return True
    return False


def _without_address(tokens: list[str]) -> list[str]:
    while tokens and tokens[-1] in _ADDRESS:
        tokens = tokens[:-1]
    return tokens


def is_stop_utterance(text: str) -> bool:
    """Stop real, incluido lo que el micrófono escribe en vez de «estop»."""
    tokens = _without_address(_norm(text).split())
    if not tokens:
        return False
    folded = " ".join(tokens)
    if utterance_ends_with_silence(folded) or is_silence_command(folded):
        return True
    if len(tokens) > 4:
        return False
    return folded in _SHORT_STOP


def is_silence_command(text: str) -> bool:
    """True si la frase es solo un stop, aunque el reconocedor lo escriba mal."""
    return _is_stop_command(_norm(text).split())


def utterance_ends_with_silence(text: str) -> bool:
    """True si el turno termina en stop, aunque venga detrás de otra frase."""
    tokens = _norm(text).split()
    if not tokens:
        return False
    if _is_stop_command(tokens):
        return True
    for size in range(1, min(4, len(tokens)) + 1):
        if _is_stop_command(tokens[-size:]):
            return True
    return False


def _is_stop_command(tokens: list[str]) -> bool:
    """True si la frase corta es un stop, con o sin el nombre."""
    if not tokens or len(tokens) > 8:
        return False
    if len(tokens) <= 4 and _STOP_SHAPE.match("".join(tokens)):
        return True
    if not any(_is_stop_word(token) for token in tokens):
        return False
    allowed = _WAKE_LEAD | _NAME_EXACT | _STOP_WORD | _GLUE | _STOP_ECHO
    return all(
        token in allowed or _is_name(token) or _is_stop_word(token) for token in tokens
    )


_GREET_LEAD = frozenset({"hola", "buenas", "buenos", "saludos", "dime"})


def _wake_index(tokens: list[str]) -> int:
    for i, token in enumerate(tokens[:-1] if len(tokens) > 1 else []):
        nxt = tokens[i + 1]
        if token in _WAKE_LEAD and _is_name(nxt):
            return i
        if token in _GREET_LEAD and _is_name(nxt):
            return i
    if len(tokens) == 1 and _is_name(tokens[0]):
        return 0
    if len(tokens) == 1 and tokens[0] in _WAKE_LEAD:
        return 0
    return -1


def _question_after(raw: str, tokens: list[str], wake_at: int) -> str:
    """Quita el aviso («ok ced») y deja la pregunta con su puntuación."""
    skip = 1 if len(tokens) == 1 else 2
    if wake_at:
        skip += wake_at
    parts = _norm(raw).split()
    if len(parts) <= skip:
        return ""
    tail = " ".join(parts[skip:])
    raw_norm = _norm(raw)
    idx = raw_norm.find(tail)
    if idx < 0:
        return tail
    return (raw or "").strip()[idx:].strip(" ,.;:¡!¿?")


def decide_cue(text: str, *, enabled: bool, listening: bool) -> tuple[str, str]:
    """off | ignore | stop | greet | answer, más el texto que debe contestar.

    ``off`` deja el turno al flujo normal. ``answer`` ya dejó a CED abierto.
    """
    raw = (text or "").strip()
    if not enabled:
        return "off", raw
    tokens = _norm(raw).split()
    if not tokens:
        return "ignore", ""
    if is_stop_utterance(raw):
        return "stop", ""
    wake_at = _wake_index(tokens)
    if wake_at >= 0:
        skip = 1 if len(tokens) == 1 else 2
        if wake_at:
            skip += wake_at
        rest = tokens[skip:]
        rest_text = " ".join(rest)
        if rest_text in _FILLER:
            return "greet", ""
        question = _question_after(raw, tokens, wake_at)
        return "answer", question or raw
    if listening:
        return "answer", raw
    return "ignore", ""
