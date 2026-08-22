"""Matching de flujos WhatsApp (palabras clave / catch-all / opt-out)."""

from __future__ import annotations

from typing import Any

from app.services.whatsapp_cloud import OPT_IN_WORDS, STOP_WORDS


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def parse_keywords(raw: str) -> list[str]:
    parts = [p.strip().lower() for p in (raw or "").replace(";", ",").split(",")]
    return [p for p in parts if p]


def is_stop_message(text: str) -> bool:
    token = _norm(text)
    return token in STOP_WORDS


def is_opt_in_message(text: str) -> bool:
    token = _norm(text)
    first = token.split(" ", 1)[0] if token else ""
    return token in OPT_IN_WORDS or first in OPT_IN_WORDS


def match_flow(
    flows: list[dict[str, Any]],
    text: str,
) -> dict[str, Any] | None:
    """Elige el primer flujo enabled por prioridad (menor número gana)."""
    body = _norm(text)
    if not body:
        return None
    active = [f for f in flows if f.get("enabled") is not False]
    active.sort(key=lambda f: int(f.get("priority") or 100))

    for flow in active:
        kind = str(flow.get("trigger_type") or "keyword").lower()
        if kind != "keyword":
            continue
        for kw in parse_keywords(str(flow.get("keywords") or "")):
            if kw == body or kw in body.split() or (len(kw) >= 4 and kw in body):
                return flow

    for flow in active:
        kind = str(flow.get("trigger_type") or "keyword").lower()
        if kind in ("catch_all", "catchall", "default"):
            return flow
    return None
