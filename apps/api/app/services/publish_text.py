"""Extrae solo el contenido publicable — sin instrucciones del usuario."""

from __future__ import annotations

import re

_INSTRUCTION_PREFIX = re.compile(
    r"^(?:"
    r"(?:que\s+)?(?:diga|dice)\s+|"
    r"(?:con\s+el\s+)?texto\s*:?\s*|"
    r"(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+que\s+diga\s+|"
    r"(?:un\s+)?post\s+que\s+diga\s+|"
    r"esto\s*:?\s*"
    r")",
    re.IGNORECASE,
)

_QUOTED = re.compile(r'^["\'](.+)["\']$')

_PUBLISH_VERB = re.compile(
    r"\b(publica|publicar|postea|postear|sube|subir|comparte|compartir)\b",
    re.I,
)
_SOCIAL_PLATFORM = re.compile(
    r"\b(instagram|insta|ig|imtagram|imstagram|facebook|fb|meta|redes)\b",
    re.I,
)
_PUBLISH_CONFIRM = re.compile(
    r"\b(env[ií]a|enviar|publica|publ[ií]calo|dale|adelante|confirmo|"
    r"s[ií]\s+publica|m[aá]ndala|mandala|hazlo|procede|env[ií]a\s+la\s+imagen|"
    r"enviar\s+publicaci[oó]n)\b",
    re.I,
)
_PUBLISH_HELP = re.compile(
    r"\b(ay[uú]da|ay[uú]dame|suger|cr[eé]ame|cr[eé]a|prop[oó]n|propone|"
    r"t[ií]tulo|descripci[oó]n|escr[ií]belo|escribe)\b",
    re.I,
)
_INLINE_CAPTION = re.compile(
    r"\b(?:con\s+el\s+|el\s+)?t[ií]tulo\s+(.+)$|"
    r"\b(?:con\s+la\s+)?descripci[oó]n\s+(.+)$|"
    r"\bque\s+diga\s+(.+)$",
    re.I,
)
_PUBLISH_ONLY = re.compile(
    r"^(?:ced\s+)?(?:publica(?:r|me|lo)?|postea(?:r|me)?|sube)\s+"
    r"(?:esta\s+)?(?:imagen|foto|esto)?\s*"
    r"(?:en\s+)?(?:mi\s+)?(?:instagram|ig|imtagram|imstagram|facebook|fb)?\s*[.!?]*$",
    re.I,
)


def strip_publish_instruction(raw: str) -> str:
    """Quita prefijos como 'que diga', 'hazme una publicación que diga'."""
    text = (raw or "").strip(" .,:;-")
    if not text:
        return ""
    for _ in range(4):
        m = _INSTRUCTION_PREFIX.match(text)
        if not m:
            break
        text = text[m.end() :].strip(" .,:;-")
    q = _QUOTED.match(text)
    if q:
        text = q.group(1).strip(" .,:;-")
    return text


def extract_publish_body(user_text: str, platform: str = "facebook") -> str:
    """Extrae cuerpo publicable desde frases naturales de voz."""
    last = (user_text or "").strip()
    if not last:
        return ""
    patterns = (
        r"\b(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+que\s+diga\s+(.+)$",
        rf"\bpublica(?:r|me|lo|que|ar)?\s+(?:en\s+)?(?:{platform}|ig|fb|instagram|facebook)\s*[:.]?\s*"
        r"(?:que\s+)?(?:diga|dice|con\s+el\s+texto|esto)?\s*[:.]?\s*(.+)$",
        r"\b(?:sube|postea)(?:r|me|lo)?\s+(?:en\s+)?(?:instagram|ig|facebook|fb)\s*[:.]?\s*"
        r"(?:que\s+)?(?:diga|dice|con\s+el\s+texto|esto)?\s*[:.]?\s*(.+)$",
        r"\b(?:publica|postea)\s*[:.]?\s*(.+)$",
    )
    for pat in patterns:
        m = re.search(pat, last, re.I)
        if m and m.group(1):
            body = strip_publish_instruction(m.group(1))
            if body:
                return body
    quoted = re.search(r'["\'](.+?)["\']', last)
    if quoted and quoted.group(1).strip():
        return strip_publish_instruction(quoted.group(1))
    return strip_publish_instruction(last)


def is_social_publish_intent(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_PUBLISH_VERB.search(t) and (_SOCIAL_PLATFORM.search(t) or re.search(r"\b(imagen|foto|esto)\b", t, re.I)))


def detect_publish_platform(text: str) -> str:
    t = (text or "").strip()
    if re.search(r"\b(facebook|fb)\b", t, re.I):
        return "facebook"
    if re.search(r"\b(instagram|insta|ig|imtagram|imstagram)\b", t, re.I):
        return "instagram"
    return "instagram"


def is_publish_confirm(text: str) -> bool:
    return bool(_PUBLISH_CONFIRM.search((text or "").strip()))


def is_publish_help_request(text: str) -> bool:
    return bool(_PUBLISH_HELP.search((text or "").strip()))


def extract_inline_publish_caption(text: str, platform: str = "instagram") -> str:
    t = (text or "").strip()
    if not t or _PUBLISH_ONLY.match(t):
        return ""
    match = _INLINE_CAPTION.search(t)
    if match:
        for group in match.groups():
            if group and group.strip():
                return strip_publish_instruction(group.strip())
    body = extract_publish_body(t, platform=platform)
    if not body or _PUBLISH_ONLY.match(body):
        return ""
    if _PUBLISH_VERB.search(body) and not re.search(r"[a-záéíóúñ]{4,}", body, re.I):
        return ""
    return body
