"""Intents de chat — no están cableados a voz ni a text_chat en este spike."""

from __future__ import annotations

import re

_SEAL = re.compile(
    r"(?i)\b("
    r"sella(?:r)?(?:lo|la|me)?|"
    r"sello\s+(?:esto|eso|el\s+pdf)|"
    r"ced\s*shield|"
    r"certifica(?:r)?\s+(?:esto|eso|el\s+pdf|el\s+documento)|"
    r"compromiso\s+(?:en\s+)?midnight"
    r")\b"
)


def is_shield_seal_intent(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 5:
        return False
    return bool(_SEAL.search(t))
