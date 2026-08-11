"""Planes de acción / crecimiento de franquicia FitLine (Oportunidades)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.services import supabase_db

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "Plan de crecimiento de mi franquicia"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client():
    return supabase_db._client()


def get_active_plan(user_id: str) -> dict[str, Any] | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    try:
        result = (
            _client()
            .table("fitline_action_plans")
            .select("*")
            .eq("user_id", uid)
            .eq("status", "active")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        logger.exception("[FITLINE-PLAN] get_active failed user=%s", uid[:8])
        return None


def list_plans(user_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    uid = (user_id or "").strip()
    if not uid:
        return []
    try:
        result = (
            _client()
            .table("fitline_action_plans")
            .select("*")
            .eq("user_id", uid)
            .order("updated_at", desc=True)
            .limit(max(1, min(limit, 50)))
            .execute()
        )
        return list(result.data or [])
    except Exception:  # noqa: BLE001
        logger.exception("[FITLINE-PLAN] list failed user=%s", uid[:8])
        return []


def upsert_active_plan(
    user_id: str,
    *,
    title: str | None = None,
    content: dict[str, Any] | None = None,
    merge_content: bool = True,
) -> dict[str, Any]:
    """Crea o actualiza el plan activo del usuario."""
    uid = (user_id or "").strip()
    if not uid:
        return {"ok": False, "error": "missing_user"}

    clean_title = (title or DEFAULT_TITLE).strip()[:200] or DEFAULT_TITLE
    incoming = content if isinstance(content, dict) else {}
    existing = get_active_plan(uid)

    if existing:
        prev = existing.get("content") if isinstance(existing.get("content"), dict) else {}
        if merge_content:
            merged = {**prev, **incoming}
            # Listas de pasos: si vienen steps nuevos, reemplazan.
            if "steps" in incoming:
                merged["steps"] = incoming.get("steps") or []
        else:
            merged = incoming
        try:
            result = (
                _client()
                .table("fitline_action_plans")
                .update(
                    {
                        "title": clean_title,
                        "content": merged,
                        "updated_at": _now_iso(),
                    }
                )
                .eq("id", existing["id"])
                .eq("user_id", uid)
                .execute()
            )
            row = (result.data or [None])[0] or {**existing, "title": clean_title, "content": merged}
            return {"ok": True, "created": False, "plan": row}
        except Exception as exc:  # noqa: BLE001
            logger.exception("[FITLINE-PLAN] update failed user=%s", uid[:8])
            return {"ok": False, "error": "save_failed", "detail": str(exc)[:160]}

    payload = {
        "user_id": uid,
        "title": clean_title,
        "status": "active",
        "content": incoming or {
            "goals": [],
            "steps": [],
            "notes": "",
            "franchise_focus": "FitLine / PM International",
        },
        "updated_at": _now_iso(),
    }
    try:
        result = _client().table("fitline_action_plans").insert(payload).execute()
        row = (result.data or [None])[0]
        if not row:
            return {"ok": False, "error": "insert_empty"}
        return {"ok": True, "created": True, "plan": row}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[FITLINE-PLAN] insert failed user=%s", uid[:8])
        return {"ok": False, "error": "save_failed", "detail": str(exc)[:160]}


def archive_active_plan(user_id: str) -> dict[str, Any]:
    uid = (user_id or "").strip()
    plan = get_active_plan(uid)
    if not plan:
        return {"ok": True, "archived": False}
    try:
        _client().table("fitline_action_plans").update(
            {"status": "archived", "updated_at": _now_iso()}
        ).eq("id", plan["id"]).eq("user_id", uid).execute()
        return {"ok": True, "archived": True, "id": plan["id"]}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[FITLINE-PLAN] archive failed user=%s", uid[:8])
        return {"ok": False, "error": "archive_failed", "detail": str(exc)[:160]}


def format_plan_spoken(plan: dict[str, Any] | None) -> str:
    if not plan:
        return (
            "Aún no tienes un plan de crecimiento de franquicia guardado. "
            "Si quieres, lo armamos juntos ahora."
        )
    content = plan.get("content") if isinstance(plan.get("content"), dict) else {}
    goals = content.get("goals") or []
    steps = content.get("steps") or []
    title = str(plan.get("title") or DEFAULT_TITLE)
    parts = [f"Tu plan «{title}» está guardado."]
    if goals:
        g = ", ".join(str(x) for x in goals[:3])
        parts.append(f"Metas: {g}.")
    if steps:
        s = "; ".join(str(x) for x in steps[:4])
        parts.append(f"Próximos pasos: {s}.")
    parts.append("Puedes verlo en Oportunidades, sección OPPS.")
    return " ".join(parts)


def build_plan_content_from_voice(
    *,
    metas: list[str] | None = None,
    pasos: list[str] | None = None,
    notas: str | None = None,
    horizonte: str | None = None,
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "franchise_focus": "FitLine / PM International",
        "terminology": "franquicia",
    }
    if metas:
        content["goals"] = [str(m).strip()[:200] for m in metas if str(m).strip()][:8]
    if pasos:
        content["steps"] = [str(p).strip()[:240] for p in pasos if str(p).strip()][:12]
    if notas and str(notas).strip():
        content["notes"] = str(notas).strip()[:2000]
    if horizonte and str(horizonte).strip():
        content["horizon"] = str(horizonte).strip()[:80]
    return content
