"""Pedido de enlace de inscripción PM/FitLine → abrir OPPS y guiar."""

from __future__ import annotations

import re
from typing import Any

FITLINE_ENROLL_GUIDE = (
    "Le abro Oportunidades, señor. "
    "Baje hasta el final de la ficha FitLine: ahí está el botón de inscripción. "
    "Dele clic y complete el registro en la plataforma de PM International, paso a paso. "
    "Si ya se inscribió y quiere su propio enlace de patrocinio, en esa misma sección puede editarlo."
)

FITLINE_ENROLL_OPEN_MODULE: dict[str, str] = {
    "module": "opportunities",
    "opportunity_id": "fitline_pm",
    "highlight": "signup",
}

# URL genérico oficial — NUNCA pegarlo; el botón de OPPS lleva el enlace de patrocinio.
_GENERIC_PM_SIGNUP_URL = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?pm-international\.com/[^\s<>\]\)\"']*registr[^\s<>\]\)\"']*"
)

_EXPLICIT_ENROLL = re.compile(
    r"(?is)\b(?:"
    r"(?:enlace|link|url|liga)\s+(?:de\s+)?(?:inscripci[oó]n|registro|patrocinio)|"
    r"(?:inscripci[oó]n|registro|patrocinio)\s+(?:de\s+)?(?:enlace|link|url|liga)|"
    r"inscribir(?:me|se|nos)?|"
    r"c[oó]mo\s+(?:me\s+)?(?:inscribo|registro|uno)|"
    r"d[oó]nde\s+(?:me\s+)?(?:inscribo|registro|uno)|"
    r"quiero\s+(?:inscribirme|registrarme|unirme|afiliarme)|"
    r"activar\s+(?:mi\s+)?franquicia|"
    r"abrir\s+(?:el\s+)?(?:m[oó]dulo\s+de\s+)?oportunidades|"
    r"abre(?:me)?\s+(?:opps|oportunidades)|"
    r"registr(?:arme|arme|arse)\s+(?:en\s+)?(?:pm|fitline|fit\s*line)|"
    r"unirme\s+(?:a\s+)?(?:pm|fitline|fit\s*line|la\s+franquicia)|"
    r"p[aá]gina\s+de\s+(?:inscripci[oó]n|registro)|"
    r"formulario\s+de\s+(?:inscripci[oó]n|registro)"
    r")\b",
)

# «dame la descripción/enlace», «pásame el link», «quiero el url»
_ASK_LINK = re.compile(
    r"(?is)\b(?:dame|pasa(?:me)?|quiero|necesito|muestra(?:me)?|abre(?:me)?|"
    r"env[ií]a(?:me)?|manda(?:me)?|comparte(?:me)?|pon(?:me)?|busca(?:me)?)\b"
    r".{0,90}\b(?:enlace|link|url|liga)\b"
)

_DESC_SLASH_LINK = re.compile(
    r"(?is)descripci[oó]n\s*/\s*(?:enlace|link|url)|"
    r"(?:enlace|link|url)\s*/\s*descripci[oó]n"
)

_SIGNUP_HINT = re.compile(
    r"(?is)\b(?:"
    r"inscripci[oó]n|inscribir(?:me|se)?|registro|registr(?:arme|arme)|"
    r"patrocinio|afiliaci[oó]n|unirme"
    r")\b"
)

_PM_BRAND = re.compile(
    r"(?is)\b(?:"
    r"fitline|fit\s*line|pm[\s\-]?internationa?l|pm-international|"
    r"patrocinio|franquicia"
    r")\b"
)

# Pregunta informativa: no abrir OPPS si no piden el enlace.
_INFO_NOT_ENROLL = re.compile(
    r"(?is)\b(?:"
    r"requisitos?|"
    r"qu[eé]\s+(?:se\s+necesita|cuesta|es\s+la\s+inscripci)|"
    r"precio\s+de\s+(?:la\s+)?inscripci|"
    r"c[oó]mo\s+funciona\s+(?:la\s+)?inscripci"
    r")\b"
)


def reply_leaks_generic_pm_signup(reply: str) -> bool:
    """True si el modelo pegó el URL genérico de registro de PM International."""
    return bool(_GENERIC_PM_SIGNUP_URL.search(reply or ""))


def _history_blob(history: list[dict[str, str]] | None) -> str:
    parts: list[str] = []
    for row in (history or [])[-8:]:
        content = str(row.get("content") or "").strip()
        if content:
            parts.append(content)
    return " ".join(parts)


def _has_pm_brand(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _PM_BRAND.search(t):
        return True
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            wants_fitline_knowledge,
        )

        return wants_fitline_knowledge(t)
    except Exception:  # noqa: BLE001
        return False


def wants_fitline_enroll_link(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    """True si piden inscribirse o el enlace — abrir OPPS, nunca pegar URL genérico."""
    t = (text or "").strip()
    if len(t) < 6:
        return False
    if _GENERIC_PM_SIGNUP_URL.search(t):
        return True
    if _EXPLICIT_ENROLL.search(t):
        if _INFO_NOT_ENROLL.search(t) and not _ASK_LINK.search(t) and not _DESC_SLASH_LINK.search(t):
            return False
        return True

    asks_link = bool(_ASK_LINK.search(t) or _DESC_SLASH_LINK.search(t))
    signupish = bool(_SIGNUP_HINT.search(t))
    branded = _has_pm_brand(t) or _has_pm_brand(_history_blob(history))

    if asks_link and branded:
        return True
    if asks_link and signupish:
        return True
    if signupish and branded and not _INFO_NOT_ENROLL.search(t):
        return True
    return False


def push_fitline_enroll_client_action(user_id: str) -> None:
    from app.services import voice_client_session as vcs

    vcs.push_client_action(user_id, "open_module", dict(FITLINE_ENROLL_OPEN_MODULE))


def try_fitline_enroll_turn(
    user_id: str | None,
    text: str,
    *,
    history: list[dict[str, str]] | None = None,
    push_voice: bool = False,
) -> dict[str, Any] | None:
    """Si el turno pide inscripción, abre OPPS y devuelve la guía (sin pegar el URL)."""
    if not wants_fitline_enroll_link(text, history):
        return None
    if push_voice and user_id:
        try:
            push_fitline_enroll_client_action(user_id)
        except Exception:  # noqa: BLE001
            pass
    return {
        "spoken": FITLINE_ENROLL_GUIDE,
        "open_module": dict(FITLINE_ENROLL_OPEN_MODULE),
    }


def maybe_force_enroll_if_signup_leak(
    user_id: str | None,
    reply: str,
    *,
    push_voice: bool = False,
) -> dict[str, Any] | None:
    """Si la respuesta ya pegó el URL genérico de PM, sustituir por guía OPPS."""
    if not reply_leaks_generic_pm_signup(reply):
        return None
    if push_voice and user_id:
        try:
            push_fitline_enroll_client_action(user_id)
        except Exception:  # noqa: BLE001
            pass
    return {
        "spoken": FITLINE_ENROLL_GUIDE,
        "open_module": dict(FITLINE_ENROLL_OPEN_MODULE),
    }
