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

# Cualquier URL de PM International en texto (home, /registration, partner, etc.).
_ANY_PM_URL = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?pm-international\.com(?:/[^\s<>\]\)\"']*)?"
)

_LINK_WORD = re.compile(
    r"(?is)\b(?:enlace|link|url|liga|hiperv[ií]nculo|"
    r"p[aá]gina\s+web|sitio\s+web|web\s+oficial)\b"
)

_SIGNUP_WORD = re.compile(
    r"(?is)\b(?:"
    r"inscripci[oó]n|inscribir(?:me|se|nos)?|"
    r"registro|registr(?:arme|arme|arse)|"
    r"patrocinio|afiliaci[oó]n|unirme|afiliar(?:me)?|"
    r"c[oó]mo\s+(?:me\s+)?(?:inscribo|registro|uno)|"
    r"d[oó]nde\s+(?:me\s+)?(?:inscribo|registro|uno)|"
    r"quiero\s+(?:inscribirme|registrarme|unirme|entrar|empezar)|"
    r"activar\s+(?:mi\s+)?franquicia|"
    r"abrir\s+(?:el\s+)?(?:m[oó]dulo\s+de\s+)?oportunidades|"
    r"[aá]bre(?:me)?\s+(?:opps|oportunidades)|"
    r"p[aá]gina\s+de\s+(?:inscripci[oó]n|registro)|"
    r"formulario\s+de\s+(?:inscripci[oó]n|registro)"
    r")\b"
)

_INFO_NOT_ENROLL = re.compile(
    r"(?is)\b(?:"
    r"requisitos?|"
    r"qu[eé]\s+(?:se\s+necesita|cuesta|es\s+la\s+inscripci)|"
    r"precio\s+de\s+(?:la\s+)?inscripci|"
    r"c[oó]mo\s+funciona\s+(?:la\s+)?inscripci"
    r")\b"
)


def reply_leaks_generic_pm_signup(reply: str) -> bool:
    """True si el modelo pegó cualquier URL de pm-international.com."""
    return bool(_ANY_PM_URL.search(reply or ""))


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
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            wants_fitline_knowledge,
        )

        if wants_fitline_knowledge(t):
            return True
    except Exception:  # noqa: BLE001
        pass
    return bool(
        re.search(
            r"(?is)\b(?:fitline|fit\s*line|pm[\s\-]?internationa[l]|pm-international|"
            r"patrocinio|franquicia)\b",
            t,
        )
    )


def wants_fitline_enroll_link(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    """Cualquier pedido razonable de enlace/inscripción PM → abrir OPPS.

    No exige una frase exacta: «dame el enlace de PM International»,
    «cuál es el link», «quiero inscribirme», etc.
    """
    t = (text or "").strip()
    if len(t) < 4:
        return False
    if _ANY_PM_URL.search(t):
        return True

    has_link = bool(_LINK_WORD.search(t))
    has_signup = bool(_SIGNUP_WORD.search(t))
    branded = _has_pm_brand(t) or _has_pm_brand(_history_blob(history))

    # Pedir el enlace/link/url de PM o FitLine (cualquier verbo o «cuál es»).
    if has_link and branded:
        return True
    # «enlace de inscripción» aunque no nombren la marca en este turno.
    if has_link and has_signup:
        return True
    # Inscribirse / registrarse en PM, salvo pregunta informativa sin pedir el link.
    if has_signup and branded:
        if _INFO_NOT_ENROLL.search(t) and not has_link:
            return False
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
    """Si la respuesta pegó un URL de PM International, sustituir por guía OPPS."""
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
