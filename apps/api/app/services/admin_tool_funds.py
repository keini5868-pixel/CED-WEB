"""Saldos y estado de herramientas — solo super admin. Nunca expone claves."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings

_SECRET_MARKERS = ("sk-", "rk_", "key-", "Bearer ", "x-api-key")


def _configured(value: str) -> bool:
    return bool((value or "").strip())


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    blob = str(data)
    for marker in _SECRET_MARKERS:
        if marker in blob:
            data["detail"] = "oculto"
    return data


def _openai_row() -> dict[str, Any]:
    settings = get_settings()
    key = settings.openai_api_key.strip()
    row = {
        "id": "openai",
        "label": "OpenAI",
        "use": "Voz Realtime y algo de chat/imagen",
        "configured": _configured(key),
        "funds": "unknown",
        "summary": "Sin clave en Railway." if not key else "Clave presente. El saldo está en OpenAI.",
        "billing_url": "https://platform.openai.com/settings/organization/billing",
        "billing_note": "Ahí ves crédito, factura y el nivel (Construir / Lanzar / Crecer).",
    }
    if not key:
        return row
    try:
        with httpx.Client(timeout=8.0) as client:
            res = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        if res.status_code == 200:
            row["funds"] = "ok"
            row["summary"] = "Clave válida. Revisa crédito y fecha de corte en Billing."
        elif res.status_code in {401, 403}:
            row["funds"] = "missing"
            row["summary"] = "La clave no pasa. Revisa OPENAI_API_KEY."
        else:
            row["summary"] = f"Clave presente. OpenAI respondió {res.status_code}."
    except Exception as exc:  # noqa: BLE001
        row["summary"] = f"Clave presente. No pude leer estado: {str(exc)[:120]}"
    return row


def _key_only(
    *,
    tool_id: str,
    label: str,
    use: str,
    key: str,
    billing_url: str,
    billing_note: str,
) -> dict[str, Any]:
    ok = _configured(key)
    return {
        "id": tool_id,
        "label": label,
        "use": use,
        "configured": ok,
        "funds": "ok" if ok else "missing",
        "summary": "Clave presente. El saldo y la fecha de corte están en su panel."
        if ok
        else "Falta la clave en Railway.",
        "billing_url": billing_url,
        "billing_note": billing_note,
    }


def _tavily_row() -> dict[str, Any]:
    settings = get_settings()
    key = settings.tavily_api_key.strip()
    row = _key_only(
        tool_id="tavily",
        label="Tavily",
        use="Búsqueda web en chat y voz",
        key=key,
        billing_url="https://app.tavily.com",
        billing_note="Usage y créditos del mes.",
    )
    if not key:
        return row
    for url in ("https://api.tavily.com/usage", "https://api.tavily.com/v1/usage"):
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url, headers={"Authorization": f"Bearer {key}"})
            if res.status_code != 200:
                continue
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            if isinstance(data, dict) and data:
                leftover = (
                    data.get("credits_remaining")
                    or data.get("remaining")
                    or data.get("credits")
                )
                if leftover is not None:
                    row["summary"] = f"Créditos/resto reportado: {leftover}."
                    row["funds"] = "low" if float(leftover) < 50 else "ok"
                else:
                    row["summary"] = "Tavily respondió uso. Detalle en su panel."
                return row
        except Exception:
            continue
    return row


def _stripe_row() -> dict[str, Any]:
    settings = get_settings()
    key = settings.stripe_secret_key.strip()
    row = {
        "id": "stripe",
        "label": "Stripe",
        "use": "Lo que te pagan los clientes (planes y recargas)",
        "configured": _configured(key),
        "funds": "missing" if not key else "ok",
        "summary": "Falta STRIPE_SECRET_KEY." if not key else "Clave presente.",
        "billing_url": "https://dashboard.stripe.com/balance",
        "billing_note": "No es un gasto de CED. Es cobro a usuarios.",
    }
    if not key:
        return row
    try:
        import stripe

        stripe.api_key = key
        bal = stripe.Balance.retrieve()
        available = 0
        pending = 0
        for item in getattr(bal, "available", None) or []:
            available += int(getattr(item, "amount", 0) or 0)
        for item in getattr(bal, "pending", None) or []:
            pending += int(getattr(item, "amount", 0) or 0)
        mode = "live" if key.startswith("sk_live_") else "test"
        row["summary"] = (
            f"Disponible ${available / 100:.2f}. Pendiente ${pending / 100:.2f}. "
            f"Modo {mode}."
        )
        row["funds"] = "ok"
    except Exception as exc:  # noqa: BLE001
        row["summary"] = f"Clave presente. No pude leer el saldo: {str(exc)[:120]}"
        row["funds"] = "unknown"
    return row


def _railway_row() -> dict[str, Any]:
    return {
        "id": "railway",
        "label": "Railway",
        "use": "Servidor de CED (API y web)",
        "configured": True,
        "funds": "unknown",
        "summary": "El crédito y la fecha de corte están en Railway → Usage.",
        "billing_url": "https://railway.app/dashboard",
        "billing_note": "Revisa Usage y Billing del proyecto CED-WEB.",
    }


def snapshot() -> dict[str, Any]:
    settings = get_settings()
    tools = [
        _openai_row(),
        _key_only(
            tool_id="anthropic",
            label="Anthropic",
            use="Chat, DMs de Instagram (Haiku) y análisis",
            key=settings.anthropic_api_key,
            billing_url="https://console.anthropic.com/settings/billing",
            billing_note="Crédito y factura del mes.",
        ),
        _key_only(
            tool_id="gemini",
            label="Google Gemini",
            use="Chat, DMs de respaldo y voz",
            key=settings.google_api_key,
            billing_url="https://aistudio.google.com/",
            billing_note="Si usas AI Studio, el cupo está ahí. Si es Cloud, en Google Cloud Billing.",
        ),
        _key_only(
            tool_id="ideogram",
            label="Ideogram",
            use="Imágenes del chat",
            key=settings.ideogram_api_key,
            billing_url="https://developer.ideogram.ai/",
            billing_note="Créditos de generación.",
        ),
        _tavily_row(),
        _key_only(
            tool_id="retell",
            label="Retell",
            use="Llamadas de voz",
            key=settings.retell_api_key,
            billing_url="https://www.retellai.com/dashboard",
            billing_note="Minutos y factura en Billing.",
        ),
        _key_only(
            tool_id="elevenlabs",
            label="ElevenLabs",
            use="Voz clonada (si está activa)",
            key=settings.elevenlabs_api_key,
            billing_url="https://elevenlabs.io/app/subscription",
            billing_note="Caracteres / plan.",
        ),
        _stripe_row(),
        _key_only(
            tool_id="supabase",
            label="Supabase",
            use="Base de datos y login",
            key=settings.supabase_service_role_key,
            billing_url="https://supabase.com/dashboard",
            billing_note="Usage del proyecto.",
        ),
        _railway_row(),
    ]
    return {
        "ok": True,
        "admin_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tools": [_clean(row) for row in tools],
        "note": (
            "Solo tú ves esto. Las fechas de corte exactas las pone cada proveedor; "
            "CED te dice si hay clave y, cuando puede, un saldo."
        ),
    }
