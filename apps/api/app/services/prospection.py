"""Modo prospección — leads Instagram + HUD."""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services import supabase_db

logger = logging.getLogger(__name__)

LEAD_KEYWORDS = re.compile(
    r"\b(info|informaci[oó]n|precio|precios|cu[aá]nto|cuesta|interesad[oa]|"
    r"dm|mensaje|contacto|whatsapp|wa\.me|comprar|quiero|necesito|"
    r"disponible|cotizaci[oó]n|servicio|curso|programa)\b",
    re.IGNORECASE,
)


def _client():
    return supabase_db._client()


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
        return {"ok": True, "enabled": True, "scan": {"ok": True, "pending": True}}
    return {"ok": True, "enabled": False}


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
    spoken = "Señor, " + " ".join(lines) if lines else "Señor, no hay leads hoy."
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


def scan_instagram_leads(user_id: str) -> dict[str, Any]:
    """Escanea comentarios recientes de IG si hay conexión Meta."""
    conn = supabase_db.get_meta_connection(user_id)
    if not conn or not conn.get("access_token"):
        return {"ok": False, "error": "Instagram no conectado", "new_leads": 0}

    token = str(conn["access_token"])
    ig_id = conn.get("ig_user_id")
    if not ig_id:
        return {"ok": False, "error": "Cuenta IG no vinculada", "new_leads": 0}

    new_count = 0
    try:
        with httpx.Client(timeout=15.0) as client:
            media_res = client.get(
                f"https://graph.facebook.com/v21.0/{ig_id}/media",
                params={
                    "fields": "id,caption,timestamp",
                    "limit": 5,
                    "access_token": token,
                },
            )
            media_items = (media_res.json().get("data") or [])[:3]
            for media in media_items:
                mid = media.get("id")
                if not mid:
                    continue
                comments_res = client.get(
                    f"https://graph.facebook.com/v21.0/{mid}/comments",
                    params={
                        "fields": "id,text,username,timestamp",
                        "limit": 25,
                        "access_token": token,
                    },
                )
                for comment in comments_res.json().get("data") or []:
                    text = str(comment.get("text") or "")
                    username = str(comment.get("username") or "user")
                    if not LEAD_KEYWORDS.search(text):
                        continue
                    score, is_hot, intent = _score_comment(text)
                    insert_lead(
                        user_id,
                        f"@{username}",
                        score=score,
                        is_hot=is_hot,
                        intent=intent[:120],
                    )
                    new_count += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PROSPECTION] scan %s", exc)
        return {"ok": False, "error": str(exc), "new_leads": new_count}

    return {"ok": True, "new_leads": new_count}
