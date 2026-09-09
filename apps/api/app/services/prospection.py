"""Modo prospección — leads Instagram + HUD."""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Any

from app.services import supabase_db

LEAD_KEYWORDS = re.compile(
    r"\b(info|informaci[oó]n|precio|precios|cu[aá]nto|cuesta|interesad[oa]|"
    r"dm|mensaje|contacto|whatsapp|wa\.me|comprar|quiero|necesito|"
    r"disponible|cotizaci[oó]n|servicio|curso|programa)\b",
    re.IGNORECASE,
)

_MODE_COMMAND = re.compile(
    r"\b(?:activa(?:r)?|enciende(?:r)?|prende(?:r)?|abre(?:r)?|desactiva(?:r)?)\b"
    r".{0,48}\bprospecci[oó]n\b"
    r"|\bmodo\s+(?:de\s+)?prospecci[oó]n\b"
    r"|\breporte\s+(?:de\s+)?(?:leads|prospecci[oó]n)\b"
    r"|\b(?:leads|prospecci[oó]n)\s+de\s+hoy\b",
    re.IGNORECASE,
)


def is_prospection_mode_command(text: str) -> bool:
    """True solo si piden activar/apagar/reporte — no copy ni ideas de prospección."""
    return bool(_MODE_COMMAND.search((text or "").strip()))


def _client():
    return supabase_db._client()


def _instagram_connected(user_id: str) -> bool:
    conn = supabase_db.get_meta_connection(user_id)
    return bool(conn and conn.get("access_token") and conn.get("ig_user_id"))


def _is_own_social_account(username: str, conn: dict[str, Any]) -> bool:
    raw = (username or "").strip().lstrip("@").lower()
    if not raw:
        return False
    names = {
        str(conn.get("ig_username") or "").lower().lstrip("@"),
        "ced",
        "ced.ev",
        "asistente virtual ced",
    }
    return raw in {n for n in names if n}


def _spoken_after_enable(user_id: str) -> str:
    conn = supabase_db.get_meta_connection(user_id)
    if conn and conn.get("access_token"):
        return (
            "Prospección activada. Escaneo comentarios de Instagram y Facebook en busca de leads."
        )
    return (
        "Prospección activada, pero Meta no está conectado. "
        "Vincula Instagram/Facebook en Conectar Redes para escanear comentarios."
    )


def scan_instagram_leads(user_id: str) -> dict[str, Any]:
    """Escanea comentarios recientes de IG y Facebook si hay conexión Meta."""
    from app.services.social_comments import fetch_social_comments

    conn = supabase_db.get_meta_connection(user_id)
    if not conn or not conn.get("access_token"):
        return {"ok": False, "error": "Instagram no conectado", "new_leads": 0}

    result = fetch_social_comments(
        user_id,
        platform="both",
        posts_limit=8,
        comments_limit=25,
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": str(result.get("error") or "scan_failed"),
            "new_leads": 0,
            "comments": 0,
        }

    comments = list(result.get("comments") or [])
    existing = {
        str(row.get("handle") or "").lower()
        for row in supabase_db.list_leads_today(user_id, limit=80)
    }
    new_count = 0
    for comment in comments:
        username = str(comment.get("username") or "usuario").strip()
        if _is_own_social_account(username, conn):
            continue
        handle = username if username.startswith("@") else f"@{username}"
        if handle.lower() in existing:
            continue
        text = str(comment.get("text") or "")
        score, is_hot, intent = _score_comment(text)
        snippet = (text[:80] or intent).strip()
        insert_lead(
            user_id,
            handle,
            platform=str(comment.get("platform") or "instagram"),
            score=score,
            is_hot=is_hot,
            intent=snippet[:120],
        )
        existing.add(handle.lower())
        new_count += 1
    return {
        "ok": True,
        "new_leads": new_count,
        "comments": len(comments),
    }


def enable_prospection_for_user(user_id: str) -> dict[str, Any]:
    """Activa con chequeo de plan. Misma puerta para voz, chat y REST."""
    from app.deps.plan_access import effective_plan_limits

    limits, reason, _ = effective_plan_limits(user_id)
    if reason == "trial_expired":
        spoken = "Tu prueba terminó. Elige un plan en Precios."
        return {"ok": False, "error": spoken, "spoken": spoken}
    if not limits.prospection_enabled:
        spoken = "La prospección requiere plan Élite o Founding. Mejora en Precios."
        return {"ok": False, "error": spoken, "spoken": spoken}
    result = set_prospection_enabled(user_id, True)
    result["spoken"] = _spoken_after_enable(user_id)
    result["instagram_connected"] = _instagram_connected(user_id)
    return result


def set_prospection_enabled(user_id: str, enabled: bool) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    _client().table("profiles").update(
        {"prospection_enabled": enabled, "updated_at": now}
    ).eq("id", user_id).execute()
    action = "prospection_on" if enabled else "prospection_off"
    supabase_db.log_ced_activity(
        user_id,
        action,
        detail="Modo prospección activado" if enabled else "Modo prospección desactivado",
    )
    if enabled:
        threading.Thread(
            target=scan_instagram_leads,
            args=(user_id,),
            daemon=True,
            name=f"prospection-scan-{user_id[:8]}",
        ).start()
        return {
            "ok": True,
            "enabled": True,
            "scan": {"ok": True, "pending": True},
            "instagram_connected": _instagram_connected(user_id),
        }
    return {"ok": True, "enabled": False, "spoken": "Prospección desactivada."}


def get_prospection_status(user_id: str) -> dict[str, Any]:
    profile = supabase_db.get_profile(user_id) or {}
    leads = supabase_db.list_leads_today(user_id, limit=10)
    hot = [l for l in leads if l.get("is_hot")]
    return {
        "ok": True,
        "enabled": bool(profile.get("prospection_enabled")),
        "leads_today": len(leads),
        "hot_leads": len(hot),
        "recent": leads[:3],
    }


def get_prospection_report(user_id: str) -> dict[str, Any]:
    status = get_prospection_status(user_id)
    leads = supabase_db.list_leads_today(user_id, limit=5)
    lines: list[str] = []
    if not status["enabled"]:
        lines.append("Prospección desactivada.")
    else:
        lines.append(f"{status['leads_today']} leads detectados hoy.")
        if status["hot_leads"]:
            lines.append(f"{status['hot_leads']} leads calientes.")
    for lead in leads:
        handle = lead.get("handle", "@?")
        score = lead.get("score", 0)
        intent = lead.get("intent") or "interés"
        hot = " 🔥" if lead.get("is_hot") else ""
        lines.append(f"{handle} score {score} — {intent}{hot}")
    spoken = " ".join(lines) if lines else "No hay leads hoy."
    return {"ok": True, "report": lines, "spoken": spoken[:480]}


def insert_lead(
    user_id: str,
    handle: str,
    *,
    platform: str = "instagram",
    score: int = 50,
    is_hot: bool = False,
    intent: str | None = None,
) -> dict[str, Any]:
    row = {
        "user_id": user_id,
        "handle": handle if handle.startswith("@") else f"@{handle}",
        "platform": platform,
        "score": max(0, min(100, score)),
        "is_hot": is_hot,
        "intent": (intent or "")[:200] or None,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    result = _client().table("detected_leads").insert(row).execute()
    supabase_db.log_ced_activity(
        user_id,
        "lead_detected",
        detail=row["handle"],
        meta={"score": row["score"], "is_hot": is_hot},
    )
    return {"ok": True, "lead": (result.data or [row])[0]}


def _score_comment(text: str) -> tuple[int, bool, str]:
    t = (text or "").strip()
    if not t:
        return 30, False, "comentario"
    matches = len(LEAD_KEYWORDS.findall(t))
    score = min(95, 40 + matches * 15)
    is_hot = score >= 70 or bool(re.search(r"\b(precio|comprar|whatsapp|urgente)\b", t, re.I))
    intent = "consulta precio" if re.search(r"\bprecio\b", t, re.I) else "interés general"
    return score, is_hot, intent

