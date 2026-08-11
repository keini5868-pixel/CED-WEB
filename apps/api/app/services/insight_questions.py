"""Captura automática de preguntas/dudas importantes (foro admin)."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_TRIVIAL = re.compile(
    r"(?is)^\s*(?:"
    r"hola|hi|hello|hey|buenas|buen\s*d[ií]a|gracias|ok|okay|vale|listo|"
    r"s[ií]|no|aja|ajá|mmm+|eh+|ah+|ya|perfecto|entendido|dale|"
    r"c[oó]mo\s+est[aá]s|qu[eé]\s+tal"
    r")[\s.!?]*$",
)

_QUESTIONISH = re.compile(
    r"(?is)(?:\?|¿|"
    r"\b(?:qu[eé]|c[oó]mo|cu[aá]ndo|d[oó]nde|por\s+qu[eé]|cu[aá]nto|"
    r"qui[eé]n|cu[aá]l|puedo|podr[ií]a|es\s+posible|funciona|"
    r"explica|dime|necesito\s+saber|no\s+entiendo|duda|confundo)\b)",
)

_BUSINESS = re.compile(
    r"(?is)\b(?:"
    r"negocio|franquicia|venta|vender|cliente|prospecto|comisi[oó]n|"
    r"ingreso|ganar|dinero|precio|costo|inversi[oó]n|patrocin|"
    r"equipo|plan|fitline|fit\s*line|pm\s*international|oportunidad|"
    r"objeci[oó]n|inscri|"
    r"producto|suplemento|ntc"
    r")\b",
)

_WEAK_ASSISTANT = re.compile(
    r"(?is)\b(?:"
    r"no\s+(?:tengo|s[eé]|puedo|cuento\s+con)|"
    r"no\s+estoy\s+seguro|"
    r"no\s+tengo\s+(?:esa\s+)?(?:info|informaci[oó]n)|"
    r"fuera\s+de\s+mi\s+(?:alcance|conocimiento)|"
    r"te\s+recomiendo\s+buscar|"
    r"no\s+puedo\s+ayudar\s+con\s+eso"
    r")\b",
)


def looks_like_valuable_question(
    text: str,
    *,
    assistant_reply: str | None = None,
) -> tuple[bool, list[str], str]:
    """Devuelve (capturar?, tags, priority)."""
    q = (text or "").strip()
    if len(q) < 18:
        return False, [], "low"
    if _TRIVIAL.match(q):
        return False, [], "low"
    if not _QUESTIONISH.search(q) and len(q) < 40:
        return False, [], "low"

    tags: list[str] = []
    priority = "normal"

    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            wants_fitline_knowledge,
        )

        if wants_fitline_knowledge(q):
            tags.append("fitline")
            priority = "high"
    except Exception:  # noqa: BLE001
        pass

    if _BUSINESS.search(q):
        if "fitline" not in tags:
            tags.append("business")
        priority = "high" if priority != "high" else priority

    if _QUESTIONISH.search(q):
        tags.append("question")

    if assistant_reply and _WEAK_ASSISTANT.search(assistant_reply):
        tags.append("weak_answer")
        priority = "high"

    if not tags and len(q) < 50:
        return False, [], "low"

    if not tags:
        tags.append("general")

    # Evitar capturar puro chitchat largo sin señal
    if tags == ["general"] and not _QUESTIONISH.search(q):
        return False, [], "low"

    return True, tags, priority


def capture_insight_question(
    user_id: str | None,
    question: str,
    *,
    channel: str = "chat",
    assistant_reply: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Persiste si la pregunta tiene valor. Best-effort (nunca rompe el chat)."""
    try:
        ok, tags, priority = looks_like_valuable_question(
            question, assistant_reply=assistant_reply
        )
        if not ok:
            return None

        from app.services import supabase_db

        client = supabase_db._client()
        row = {
            "user_id": (user_id or "").strip() or None,
            "question": (question or "").strip()[:2000],
            "channel": channel if channel in (
                "chat", "voice", "finance", "advanced", "other"
            ) else "other",
            "tags": tags,
            "priority": priority,
            "status": "new",
            "assistant_preview": (assistant_reply or "")[:500] or None,
            "metadata": metadata or {},
        }
        result = client.table("ced_insight_questions").insert(row).execute()
        rows = result.data or []
        return rows[0] if rows else row
    except Exception:  # noqa: BLE001
        logger.exception("[INSIGHT] capture failed")
        return None


def list_insight_questions(
    *,
    status: str | None = "new",
    limit: int = 50,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    from app.services import supabase_db

    client = supabase_db._client()
    q = (
        client.table("ced_insight_questions")
        .select("*")
        .order("created_at", desc=True)
        .limit(max(1, min(limit, 200)))
    )
    if status and status != "all":
        q = q.eq("status", status)
    if tag:
        q = q.contains("tags", [tag])
    try:
        result = q.execute()
        return list(result.data or [])
    except Exception:  # noqa: BLE001
        logger.exception("[INSIGHT] list failed")
        return []


def update_insight_status(question_id: str, status: str) -> dict[str, Any]:
    if status not in ("new", "reviewed", "archived"):
        return {"ok": False, "error": "invalid_status"}
    from app.services import supabase_db

    try:
        result = (
            supabase_db._client()
            .table("ced_insight_questions")
            .update({"status": status})
            .eq("id", question_id)
            .execute()
        )
        rows = result.data or []
        return {"ok": True, "row": rows[0] if rows else None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[INSIGHT] update status failed")
        return {"ok": False, "error": str(exc)}
