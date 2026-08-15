"""Enlace de patrocinio FitLine/PM — por usuario con fallback global."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings
from app.services import supabase_db

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://", re.I)
_MAX_URL = 500


def default_sponsor_url() -> str:
    return (get_settings().opportunities_fitline_sponsor_url or "").strip()


def normalize_sponsor_url(raw: str | None) -> str:
    url = (raw or "").strip()[:_MAX_URL]
    if not url or " " in url:
        return ""
    if not _URL_RE.match(url):
        url = f"https://{url}"
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return ""
    host = (parsed.netloc or "").strip().lower()
    if parsed.scheme not in ("http", "https") or not host or "." not in host:
        return ""
    if host.startswith(".") or host.endswith("."):
        return ""
    return url


def get_user_sponsor_url(user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        return ""
    try:
        profile = supabase_db.get_profile(uid) or {}
        own = normalize_sponsor_url(profile.get("fitline_sponsor_url"))
        if own:
            return own
    except Exception:  # noqa: BLE001
        logger.exception("[SPONSOR] get profile failed user=%s", uid[:8])
    return ""


def resolve_sponsor_url(user_id: str | None = None) -> dict[str, Any]:
    """Prioridad: enlace del usuario → env global."""
    uid = (user_id or "").strip()
    own = get_user_sponsor_url(uid) if uid else ""
    fallback = default_sponsor_url()
    url = own or fallback
    source = "user" if own else ("default" if fallback else "none")
    return {
        "url": url,
        "configured": bool(url),
        "source": source,
        "has_own": bool(own),
        "has_default": bool(fallback),
        "cta_label": "Activar su franquicia (paquete manager)",
    }


def update_user_sponsor_url(user_id: str, url: str | None) -> dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {"ok": False, "error": "missing_user"}
    normalized = normalize_sponsor_url(url) if url is not None else ""
    # Vacío explícito = borrar y volver al default global.
    value = normalized or None
    try:
        supabase_db._client().table("profiles").update(
            {"fitline_sponsor_url": value}
        ).eq("id", uid).execute()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[SPONSOR] update failed user=%s", uid[:8])
        return {"ok": False, "error": "save_failed", "detail": str(exc)[:160]}
    resolved = resolve_sponsor_url(uid)
    if value:
        try:
            from app.services.referrals import note_activity

            note_activity(uid, "sponsor")
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, **resolved, "saved_url": value or ""}
