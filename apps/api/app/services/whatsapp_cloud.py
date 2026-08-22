"""WhatsApp Cloud API — token, envío y parseo de webhooks."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset(
    {"stop", "parar", "para", "baja", "unsubscribe", "cancelar", "optout", "opt-out"}
)
OPT_IN_WORDS = frozenset({"hola", "hello", "hi", "buenas", "start", "inicio"})


class WhatsAppCloudError(Exception):
    pass


def graph_base() -> str:
    version = get_settings().meta_api_version.strip() or "v21.0"
    return f"https://graph.facebook.com/{version}"


def verify_webhook_signature(raw_body: bytes, header: str | None) -> bool:
    secret = get_settings().meta_app_secret.strip()
    if not secret:
        logger.warning("[WA] META_APP_SECRET vacío — no se verifica firma del webhook")
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    got = header.split("=", 1)[1].strip()
    return hmac.compare_digest(expected, got)


def exchange_oauth_code(code: str) -> str:
    settings = get_settings()
    app_id = settings.meta_app_id.strip()
    secret = settings.meta_app_secret.strip()
    if not app_id or not secret:
        raise WhatsAppCloudError("META_APP_ID / META_APP_SECRET no configurados.")
    url = f"{graph_base()}/oauth/access_token"
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.get(
                url,
                params={
                    "client_id": app_id,
                    "client_secret": secret,
                    "code": code.strip(),
                },
            )
            data = res.json() if res.content else {}
    except Exception as exc:  # noqa: BLE001
        raise WhatsAppCloudError("No pude canjear el código de Meta.") from exc
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise WhatsAppCloudError(
            str(data.get("error", {}).get("message") or "Meta no devolvió access_token.")
        )
    return token


def fetch_phone_numbers(waba_id: str, access_token: str) -> list[dict[str, Any]]:
    url = f"{graph_base()}/{waba_id.strip()}/phone_numbers"
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.get(url, params={"access_token": access_token})
            data = res.json() if res.content else {}
    except Exception as exc:  # noqa: BLE001
        raise WhatsAppCloudError("No pude listar números de WhatsApp.") from exc
    if res.status_code >= 400:
        raise WhatsAppCloudError(
            str(data.get("error", {}).get("message") or "Error listando números WhatsApp.")
        )
    items = data.get("data") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def subscribe_waba_webhooks(waba_id: str, access_token: str) -> None:
    url = f"{graph_base()}/{waba_id.strip()}/subscribed_apps"
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.post(url, params={"access_token": access_token})
            if res.status_code >= 400:
                logger.warning("[WA] subscribed_apps failed: %s", res.text[:300])
    except Exception:  # noqa: BLE001
        logger.warning("[WA] subscribed_apps exception", exc_info=True)


def send_text_message(
    *,
    phone_number_id: str,
    access_token: str,
    to: str,
    body: str,
) -> dict[str, Any]:
    url = f"{graph_base()}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            data = res.json() if res.content else {}
    except Exception as exc:  # noqa: BLE001
        raise WhatsAppCloudError("No pude enviar el mensaje de WhatsApp.") from exc
    if res.status_code >= 400:
        raise WhatsAppCloudError(
            str(data.get("error", {}).get("message") or "Error enviando WhatsApp.")
        )
    return data if isinstance(data, dict) else {}


def inbound_text_events(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Extrae mensajes de texto útiles del webhook Cloud API."""
    out: list[dict[str, str]] = []
    entries = payload.get("entry") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes") or []
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            phone_number_id = str(
                (value.get("metadata") or {}).get("phone_number_id") or ""
            ).strip()
            messages = value.get("messages") or []
            if not isinstance(messages, list):
                continue
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if str(msg.get("type") or "") != "text":
                    continue
                body = str((msg.get("text") or {}).get("body") or "").strip()
                wa_from = str(msg.get("from") or "").strip()
                wamid = str(msg.get("id") or "").strip()
                if not body or not wa_from or not phone_number_id:
                    continue
                out.append(
                    {
                        "phone_number_id": phone_number_id,
                        "from": wa_from,
                        "body": body,
                        "wamid": wamid,
                    }
                )
    return out
