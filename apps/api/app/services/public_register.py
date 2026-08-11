"""Registro manual email/contraseña — verificación vía Resend (no Google OAuth).

Supabase Auth SMTP está fallando con «Error sending confirmation email».
Este flujo crea el usuario con la Admin API (sin enviar correo de GoTrue) y
manda el enlace de confirmación con Resend HTTP.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlencode

from app.config import get_settings
from app.services.email_resend import (
    resend_configured,
    send_signup_verification_email,
)

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PublicRegisterError(Exception):
    def __init__(self, message: str, *, code: str = "register_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _client():
    from app.services import supabase_db

    return supabase_db._client()


def _canonical_web_url() -> str:
    settings = get_settings()
    return (settings.web_public_url or "https://ced-castillo.com").strip().rstrip("/")


def _sanitize_next(next_path: str | None) -> str:
    raw = (next_path or "/").strip() or "/"
    if not raw.startswith("/"):
        return "/"
    if raw.startswith("//") or "://" in raw:
        return "/"
    return raw[:500]


def _redirect_to(next_path: str | None) -> str:
    nxt = _sanitize_next(next_path)
    return f"{_canonical_web_url()}/auth/callback?{urlencode({'next': nxt})}"


def _find_user_id_by_email(email: str) -> str | None:
    client = _client()
    try:
        # Prefer profiles table (indexed) then Auth list fallback.
        row = (
            client.table("profiles")
            .select("id")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        data = getattr(row, "data", None) or []
        if data and data[0].get("id"):
            return str(data[0]["id"])
    except Exception:  # noqa: BLE001
        logger.warning("[REGISTER] profiles lookup failed for %s", email[:3])
    try:
        listed = client.auth.admin.list_users(page=1, per_page=200)
        users = getattr(listed, "users", None) or []
        for u in users:
            if str(getattr(u, "email", "") or "").lower() == email:
                return str(getattr(u, "id", "") or "")
    except Exception:  # noqa: BLE001
        logger.warning("[REGISTER] auth list_users failed")
    return None


def _delete_user(user_id: str) -> None:
    if not user_id:
        return
    try:
        _client().auth.admin.delete_user(user_id)
    except Exception:  # noqa: BLE001
        logger.warning("[REGISTER] rollback delete_user failed id=%s", user_id[:8])


def _generate_signup_link(
    *,
    email: str,
    password: str,
    full_name: str,
    redirect_to: str,
) -> tuple[str, str]:
    """Crea (o reutiliza) enlace de confirmación. Devuelve (action_link, user_id)."""
    client = _client()
    payload: dict[str, Any] = {
        "type": "signup",
        "email": email,
        "password": password,
        "options": {
            "data": {"full_name": full_name},
            "redirect_to": redirect_to,
        },
    }
    try:
        res = client.auth.admin.generate_link(payload)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        low = msg.lower()
        if "already" in low or "registered" in low or "exists" in low:
            raise PublicRegisterError(
                "Ya existe una cuenta con este correo. Inicia sesión o usa otro correo.",
                code="email_exists",
            ) from exc
        logger.exception("[REGISTER] generate_link failed")
        raise PublicRegisterError(
            "No se pudo preparar el registro. Intenta de nuevo en unos segundos.",
            code="generate_link_failed",
        ) from exc

    # supabase-py may return object or dict
    props = getattr(res, "properties", None) or {}
    if hasattr(res, "model_dump"):
        dumped = res.model_dump()
        props = dumped.get("properties") or dumped
    elif isinstance(res, dict):
        props = res.get("properties") or res

    action_link = str(
        (props or {}).get("action_link")
        or getattr(res, "action_link", "")
        or ""
    ).strip()
    user = getattr(res, "user", None) or (res if isinstance(res, dict) else {}).get("user")
    user_id = str(
        getattr(user, "id", None)
        or (user or {}).get("id")
        or (props or {}).get("user_id")
        or ""
    ).strip()

    if not action_link:
        raise PublicRegisterError(
            "No se pudo generar el enlace de verificación.",
            code="missing_action_link",
        )
    return action_link, user_id


def register_with_email(
    *,
    email: str,
    password: str,
    full_name: str = "",
    next_path: str | None = "/",
    offer: str | None = None,
) -> dict[str, Any]:
    if not resend_configured():
        raise PublicRegisterError(
            "El servicio de correo no está configurado (RESEND_API_KEY). "
            "El administrador debe añadirlo en Railway para completar el registro.",
            code="resend_not_configured",
        )

    email_n = (email or "").strip().lower()
    password_n = password or ""
    name_n = (full_name or "").strip()
    if not EMAIL_RE.match(email_n):
        raise PublicRegisterError("Email inválido.", code="invalid_email")
    if len(password_n) < 8:
        raise PublicRegisterError(
            "La contraseña debe tener al menos 8 caracteres.",
            code="weak_password",
        )

    existing = _find_user_id_by_email(email_n)
    if existing:
        raise PublicRegisterError(
            "Ya existe una cuenta con este correo. Inicia sesión o usa otro correo.",
            code="email_exists",
        )

    redirect_to = _redirect_to(next_path)
    action_link, user_id = _generate_signup_link(
        email=email_n,
        password=password_n,
        full_name=name_n,
        redirect_to=redirect_to,
    )

    ok, err = send_signup_verification_email(
        to_email=email_n,
        full_name=name_n,
        action_link=action_link,
    )
    if not ok:
        _delete_user(user_id)
        logger.error("[REGISTER] Resend failed email=%s err=%s", email_n, err)
        raise PublicRegisterError(
            "No pudimos enviar el correo de verificación. "
            "Revisa que Resend acepte el dominio de CED, o intenta más tarde.",
            code="email_send_failed",
        )

    offer_n = (offer or "").strip().lower()
    cierre_trial: dict[str, Any] | None = None
    if offer_n in ("cierre", "fitline") and user_id:
        import time

        from app.services import supabase_db

        # El trigger handle_new_user puede tardar un instante en crear la fila.
        for _ in range(5):
            time.sleep(0.4)
            cierre_trial = supabase_db.apply_cierre_fitline_trial(user_id)
            if cierre_trial.get("ok"):
                break
        logger.info(
            "[REGISTER] cierre fitline trial user=%s result=%s",
            user_id[:8],
            (cierre_trial or {}).get("reason") or (cierre_trial or {}).get("ok"),
        )

    logger.info(
        "[REGISTER] ok email=%s user=%s via=resend offer=%s",
        email_n,
        (user_id or "?")[:8],
        offer_n or "-",
    )
    out: dict[str, Any] = {
        "ok": True,
        "email": email_n,
        "needs_verification": True,
        "message": "Te enviamos un enlace de verificación. Revisa tu correo.",
    }
    if cierre_trial and cierre_trial.get("ok"):
        out["offer"] = "cierre"
        out["trial_hours"] = cierre_trial.get("hours", 24)
        out["trial_voice_minutes"] = cierre_trial.get(
            "minutes_daily", 15
        )
        out["message"] = (
            "Te enviamos un enlace de verificación. "
            "Al confirmar tendrás 15 min de voz en las primeras 24 horas "
            "(no se renuevan; FitLine / CED PM International)."
        )
    return out


def resend_verification_email(
    *,
    email: str,
    next_path: str | None = "/",
) -> dict[str, Any]:
    if not resend_configured():
        raise PublicRegisterError(
            "El servicio de correo no está configurado (RESEND_API_KEY).",
            code="resend_not_configured",
        )
    email_n = (email or "").strip().lower()
    if not EMAIL_RE.match(email_n):
        raise PublicRegisterError("Email inválido.", code="invalid_email")

    client = _client()
    user_id = _find_user_id_by_email(email_n)
    if not user_id:
        # Anti-enumeración: respuesta genérica de éxito.
        return {
            "ok": True,
            "message": "Si el correo existe y falta confirmar, enviamos un nuevo enlace.",
        }

    try:
        user_res = client.auth.admin.get_user_by_id(user_id)
        user = getattr(user_res, "user", None) or user_res
        confirmed = getattr(user, "email_confirmed_at", None) or (
            user.get("email_confirmed_at") if isinstance(user, dict) else None
        )
        if confirmed:
            return {
                "ok": True,
                "message": "Esta cuenta ya está verificada. Puedes iniciar sesión.",
                "already_verified": True,
            }
        meta = getattr(user, "user_metadata", None) or (
            user.get("user_metadata") if isinstance(user, dict) else {}
        ) or {}
        full_name = str(meta.get("full_name") or "")
    except Exception:  # noqa: BLE001
        full_name = ""

    redirect_to = _redirect_to(next_path)
    try:
        res = client.auth.admin.generate_link(
            {
                "type": "magiclink",
                "email": email_n,
                "options": {"redirect_to": redirect_to},
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[REGISTER] resend generate_link failed")
        raise PublicRegisterError(
            "No se pudo reenviar el correo. Intenta de nuevo.",
            code="generate_link_failed",
        ) from exc

    props = getattr(res, "properties", None) or {}
    if hasattr(res, "model_dump"):
        dumped = res.model_dump()
        props = dumped.get("properties") or dumped
    elif isinstance(res, dict):
        props = res.get("properties") or res
    action_link = str((props or {}).get("action_link") or "").strip()
    if not action_link:
        raise PublicRegisterError(
            "No se pudo generar el enlace de verificación.",
            code="missing_action_link",
        )

    ok, err = send_signup_verification_email(
        to_email=email_n,
        full_name=full_name,
        action_link=action_link,
    )
    if not ok:
        logger.error("[REGISTER] resend email failed email=%s err=%s", email_n, err)
        raise PublicRegisterError(
            "No pudimos reenviar el correo de verificación.",
            code="email_send_failed",
        )
    return {"ok": True, "message": "Email de verificación reenviado."}
