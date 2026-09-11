"""State firmado para OAuth Meta — evita vincular Instagram a otra cuenta CED."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from app.config import get_settings

_MAX_AGE_SEC = 15 * 60


def _secret() -> bytes:
    settings = get_settings()
    raw = settings.meta_app_secret.strip() or settings.supabase_jwt_secret.strip()
    if not raw:
        raise RuntimeError("Falta META_APP_SECRET o SUPABASE_JWT_SECRET para firmar OAuth.")
    return raw.encode("utf-8")


def sign_meta_oauth_state(user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("user_id vacío")
    ts = str(int(time.time()))
    nonce = secrets.token_hex(8)
    payload = f"{uid}.{ts}.{nonce}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_meta_oauth_state(state: str, *, max_age_sec: int = _MAX_AGE_SEC) -> str | None:
    raw = (state or "").strip()
    parts = raw.split(".")
    if len(parts) < 4:
        return None
    sig = parts[-1]
    nonce = parts[-2]
    ts_s = parts[-3]
    user_id = ".".join(parts[:-3])
    if not user_id or not nonce or not sig:
        return None
    try:
        ts = int(ts_s)
    except ValueError:
        return None
    if abs(time.time() - ts) > max_age_sec:
        return None
    payload = f"{user_id}.{ts_s}.{nonce}"
    expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    return user_id
