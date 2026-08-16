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

_EXPLICIT_ENROLL = re.compile(
    r"(?is)\b(?:"
    r"enlace\s+(?:de\s+)?(?:inscripci[oó]n|registro|patrocinio)|"
    r"link\s+(?:de\s+)?(?:inscripci[oó]n|registro|patrocinio)|"
    r"inscribir(?:me|se)|c[oó]mo\s+(?:me\s+)?inscribo|"
    r"d[oó]nde\s+(?:me\s+)?inscribo|"
    r"activar\s+(?:mi\s+)?franquicia|"
    r"abrir\s+(?:el\s+)?(?:m[oó]dulo\s+de\s+)?oportunidades|"
    r"abre(?:me)?\s+(?:opps|oportunidades)|"
    r"registr(?:arme|arme)\s+(?:en\s+)?(?:pm|fitline|fit\s*line)"
    r")\b",
)

_ASK_LINK = re.compile(
    r"(?is)\b(?:dame|pasa(?:me)?|quiero|necesito|muestra(?:me)?|abre(?:me)?)\s+"
    r"(?:el\s+)?(?:enlace|link)\b",
)


def wants_fitline_enroll_link(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    """True si piden el enlace de inscripción o abrir OPPS para registrarse."""
    t = (text or "").strip()
    if len(t) < 8:
        return False
    if _EXPLICIT_ENROLL.search(t):
        return True
    if not _ASK_LINK.search(t):
        return False
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            wants_fitline_knowledge,
        )
    except Exception:  # noqa: BLE001
        return False
    if wants_fitline_knowledge(t):
        return True
    blob_parts: list[str] = [t]
    for row in (history or [])[-6:]:
        content = str(row.get("content") or "").strip()
        if content:
            blob_parts.append(content)
    return wants_fitline_knowledge(" ".join(blob_parts))


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
