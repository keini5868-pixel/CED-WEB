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
    r"equipo|plan\s+de\s+compensaci[oó]n|fitline|fit\s*line|"
    r"pm\s*international|pm\s*internacional|"
    r"oportunidad|"
    r"objeci[oó]n|inscri|"
    r"producto|suplemento|ntc"
    r")\b",
)

# Dudas de uso de CED (no saludos): módulos, voz, imagen, planes, fallos.
_CED_SYSTEM = re.compile(
    r"(?is)\b(?:"
    r"\bced\b|castillo|"
    r"modo\s+avanzado|chat\s+(?:de\s+)?texto|historial|"
    r"configuraci[oó]n|m[oó]dulo|oportunidades|\bopps\b|"
    r"generar\s+(?:una?\s+)?(?:imagen|pdf)|"
    r"no\s+(?:funciona|abre|deja|puedo|carga|responde)|"
    r"error|falla|bug|cuota|l[ií]mite|"
    r"plan\s+(?:b[aá]sico|pro|elite|[eé]lite|starter)|"
    r"micr[oó]fono|c[aá]mara|recarga|monedero|"
    r"c[oó]mo\s+(?:uso|usar|abro|abrir)\b"
    r")\b",
)

_PROBLEM = re.compile(
    r"(?is)\b(?:"
    r"no\s+(?:funciona|abre|deja|puedo|carga|responde|entiendo)|"
    r"error|falla|bug|problema|se\s+traba|se\s+queda"
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
        priority = "high"

    if _CED_SYSTEM.search(q):
        tags.append("ced")

    if _QUESTIONISH.search(q):
        tags.append("question")

    if assistant_reply and _WEAK_ASSISTANT.search(assistant_reply):
        tags.append("weak_answer")
        priority = "high"

    if _PROBLEM.search(q) and (
        "ced" in tags or "fitline" in tags or "business" in tags
    ):
        priority = "high"

    domain = {"fitline", "business", "ced", "weak_answer"}
    if not domain.intersection(tags):
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
        rows = list(result.data or [])
        return _attach_user_labels(rows)
    except Exception:  # noqa: BLE001
        logger.exception("[INSIGHT] list failed")
        return []


def _attach_user_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Añade email/label para que el admin vea de quién es cada pregunta."""
    ids = [str(r.get("user_id") or "") for r in rows if r.get("user_id")]
    ids = [i for i in ids if i]
    if not ids:
        return rows
    try:
        from app.services import supabase_db

        found = (
            supabase_db._client()
            .table("profiles")
            .select("id, email")
            .in_("id", list(dict.fromkeys(ids)))
            .execute()
        )
        by_id = {
            str(p.get("id")): str(p.get("email") or "").strip()
            for p in (found.data or [])
            if p.get("id")
        }
    except Exception:  # noqa: BLE001
        logger.warning("[INSIGHT] profile labels failed")
        by_id = {}
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        uid = str(item.get("user_id") or "")
        email = by_id.get(uid) or ""
        item["user_email"] = email or None
        item["user_label"] = email or (uid[:8] if uid else "anónimo")
        out.append(item)
    return out


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
