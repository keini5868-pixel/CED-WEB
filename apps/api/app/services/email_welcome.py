"""Email de bienvenida — Resend."""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_welcome_email(
    *,
    to_email: str,
    name: str,
    password: str,
    plan_label: str,
    minutes_daily: int,
    login_url: str,
) -> tuple[bool, str | None]:
    settings = get_settings()
    api_key = settings.resend_api_key.strip()
    if not api_key:
        return False, "RESEND_API_KEY no configurada"

    from_addr = settings.email_from.strip() or "CED <noreply@castillodigital.com>"
    subject = f"Bienvenido al Castillo Digital, {name.split()[0] if name else 'Usuario'}"

    html = f"""
<div style="font-family:system-ui,sans-serif;background:#0a0a0a;color:#e0f7fa;padding:32px;max-width:560px;margin:0 auto;">
  <h1 style="color:#00e5ff;font-size:22px;margin:0 0 8px;">🏰 CASTILLO DIGITAL</h1>
  <p style="color:#94a3b8;">Hola {name},</p>
  <p>¡Bienvenido a CED! Tu cuenta premium está lista.</p>
  <div style="background:#111;border:1px solid #0891b2;border-radius:8px;padding:16px;margin:20px 0;">
    <p style="margin:0 0 8px;font-size:12px;color:#67e8f9;text-transform:uppercase;letter-spacing:1px;">Tus credenciales</p>
    <p style="margin:4px 0;"><strong>Email:</strong> {to_email}</p>
    <p style="margin:4px 0;"><strong>Contraseña:</strong> {password}</p>
  </div>
  <p style="text-align:center;margin:24px 0;">
    <a href="{login_url}" style="display:inline-block;background:#0891b2;color:#fff;text-decoration:none;padding:14px 28px;border-radius:6px;font-weight:bold;">INICIAR SESIÓN</a>
  </p>
  <p><strong>Tu plan:</strong> {plan_label}<br/>
  <strong>Minutos diarios:</strong> {minutes_daily}</p>
  <p style="font-size:14px;color:#94a3b8;">
    1. Inicia sesión con las credenciales arriba<br/>
    2. Cambia tu contraseña en Configuración<br/>
    3. Activa el micrófono y di &quot;Hola CED&quot;
  </p>
  <p style="font-size:13px;color:#64748b;margin-top:24px;">
    Dudas: keini5868@gmail.com · WhatsApp +1 980-497-9987<br/>
    — Keini Castillo, Fundadora de CED
  </p>
</div>
"""

    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": from_addr,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
            if res.status_code >= 400:
                err = res.text[:200]
                logger.warning("[EMAIL] Resend %s: %s", res.status_code, err)
                return False, f"Resend error {res.status_code}"
        return True, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[EMAIL] send failed: %s", exc)
        return False, str(exc)
