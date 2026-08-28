"""Intents conversacionales → tipos cerrados de automatización."""

from __future__ import annotations

import re
from typing import Any

from app.services.automation_pilot.catalog import CURATED_CARDS

_AUTOMATION_TALK = re.compile(
    r"\b("
    r"automatiz|"
    r"cuando\s+alguien\s+coment|"
    r"cuando\s+me\s+escriban|"
    r"responde(?:le)?\s+(?:con|autom)|"
    r"palabra\s+clave|"
    r"embudo|"
    r"nurturing|"
    r"seguimiento\s+autom|"
    r"link\s+de\s+whatsapp|"
    r"reels?\b.*\b(?:coment|whatsapp)|"
    r"coment\w*.*\b(?:instagram|facebook|whatsapp|info)"
    r")\b",
    re.I,
)

_CHANNEL = {
    "instagram": re.compile(r"\b(instagram|insta|ig|reels?)\b", re.I),
    "facebook": re.compile(r"\b(facebook|messenger|fb)\b", re.I),
    "whatsapp": re.compile(r"\b(whatsapp|wa\.me|whats)\b", re.I),
}

_COMMENT = re.compile(r"\b(coment|comment)\b", re.I)
_DM = re.compile(r"\b(dm|mensaje\s+directo|messenger|inbox)\b", re.I)
_KEYWORD = re.compile(
    r"(?:palabra\s+clave|keyword|comente?\s+['\"]?(\w+)['\"]?|"
    r"diga\s+['\"]?(\w+)['\"]?)",
    re.I,
)


def is_automation_config_intent(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 12:
        return False
    return bool(_AUTOMATION_TALK.search(t))


def parse_automation_brief(text: str) -> dict[str, Any] | None:
    """Traduce NL a una tarjeta curada + overrides (lista cerrada)."""
    if not is_automation_config_intent(text):
        return None
    t = text.strip()
    channel = "instagram"
    for name, rx in _CHANNEL.items():
        if rx.search(t):
            channel = name
            break

    trigger_type = "comment_keyword"
    if _DM.search(t) and not _COMMENT.search(t):
        trigger_type = "dm_new"
    elif _COMMENT.search(t):
        trigger_type = "comment_keyword" if _KEYWORD.search(t) else "comment_any"

    if channel == "whatsapp":
        if re.search(r"fuera\s+de\s+horario|horario", t, re.I):
            card_key = "wa_outside_hours"
        elif re.search(r"caliente|comprar|intenci[oó]n", t, re.I):
            card_key = "wa_hot_lead"
        elif re.search(r"fitline|pm\s*international|opps", t, re.I):
            card_key = "wa_fitline_after_questions"
        elif re.search(r"seguimiento|no\s+responde|inactiv", t, re.I):
            card_key = "wa_followup_inactive"
        else:
            card_key = "wa_welcome"
    elif channel == "facebook":
        card_key = "fb_dm_new" if trigger_type.startswith("dm") else "fb_comment_keyword"
    else:
        card_key = "ig_dm_new" if trigger_type.startswith("dm") else "ig_comment_keyword"

    card = next((c for c in CURATED_CARDS if c["card_key"] == card_key), None)
    if not card:
        return None

    keywords: list[str] = []
    for m in re.finditer(r"['\"]([a-záéíóúñ]{2,24})['\"]", t, re.I):
        keywords.append(m.group(1).lower())
    km = _KEYWORD.search(t)
    if km:
        for g in km.groups():
            if g:
                keywords.append(g.lower())
    if not keywords and trigger_type == "comment_keyword":
        keywords = list((card.get("default_trigger") or {}).get("keywords") or ["info"])

    trigger_config = dict(card.get("default_trigger") or {})  # type: ignore[arg-type]
    if keywords:
        trigger_config["keywords"] = keywords[:8]

    action_config = dict(card.get("default_action") or {})  # type: ignore[arg-type]
    # Extraer frase de respuesta si el usuario la dicta tras "responde" / "dile".
    reply_m = re.search(
        r"(?:responde(?:le)?|dile|diga)\s+(?:con\s+)?['\"](.{8,280})['\"]",
        t,
        re.I,
    )
    if reply_m:
        action_config["reply_text"] = reply_m.group(1).strip()

    return {
        "card_key": card_key,
        "channel": channel,
        "trigger_type": str(card["trigger_type"]),
        "name": str(card["name"]),
        "trigger_config": trigger_config,
        "action_config": action_config,
        "confirmation": (
            f"Voy a crear «{card['name']}» en {channel}: "
            f"disparador {card['trigger_type']}"
            + (f" con palabras {keywords}" if keywords else "")
            + ". ¿Lo activo?"
        ),
    }
