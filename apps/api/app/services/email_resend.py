"""Envío de correo vía Resend HTTP API (verificación de registro, etc.)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def resend_configured() -> bool:
    return bool(get_settings().resend_api_key.strip())


def send_resend_email(
    *,
    to_email: str,
    subject: str,
    html: str,
    text: str | None = None,
) -> tuple[bool, str | None]:
    settings = get_settings()
    api_key = settings.resend_api_key.strip()
    if not api_key:
        return False, "RESEND_API_KEY no configurada en Railway"
    from_addr = settings.email_from.strip() or "CED <noreply@ced-castillo.com>"
    payload: dict[str, Any] = {
        "from": from_addr,
        "to": [to_email.strip()],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if res.status_code >= 400:
            err = (res.text or "")[:240]
            logger.warning("[EMAIL:RESEND] %s %s", res.status_code, err)
            return False, f"Resend error {res.status_code}: {err}"
        return True, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[EMAIL:RESEND] send failed: %s", exc)
        return False, str(exc)[:200]


def send_signup_verification_email(
    *,
    to_email: str,
    full_name: str,
    action_link: str,
) -> tuple[bool, str | None]:
    name = (full_name or "").strip() or "Usuario"
    first = name.split()[0]
    subject = "Confirma tu cuenta CED"
    html = f"""
<div style="font-family:system-ui,sans-serif;background:#0a0a0a;color:#e0f7fa;padding:32px;max-width:560px;margin:0 auto;">
  <h1 style="color:#00e5ff;font-size:22px;margin:0 0 8px;">CED — Castillo Evolución Digital</h1>
  <p style="color:#94a3b8;">Hola {first},</p>
  <p>Gracias por registrarte. Confirma tu correo para activar tu cuenta y tu prueba gratuita.</p>
  <p style="text-align:center;margin:28px 0;">
    <a href="{action_link}"
       style="display:inline-block;background:#0891b2;color:#fff;text-decoration:none;padding:14px 28px;border-radius:6px;font-weight:bold;">
      CONFIRMAR MI CORREO
    </a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    Si no creaste esta cuenta, ignora este mensaje.<br/>
    El enlace caduca según la configuración de seguridad de CED.
  </p>
</div>
"""
    text = (
        f"Hola {first},\n\n"
        f"Confirma tu cuenta CED abriendo este enlace:\n{action_link}\n\n"
        "Si no creaste esta cuenta, ignora este mensaje.\n"
    )
    return send_resend_email(
        to_email=to_email,
        subject=subject,
        html=html,
        text=text,
    )
