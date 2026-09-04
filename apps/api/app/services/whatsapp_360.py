"""WhatsApp vía 360dialog (BSP) — misma Cloud API, otro host y API key."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.whatsapp_cloud import WhatsAppCloudError

logger = logging.getLogger(__name__)

D360_BASE = "https://waba-v2.360dialog.io"


def is_360dialog(account: dict[str, Any] | None) -> bool:
    if not account:
        return False
    p = str(account.get("provider") or "meta").strip().lower()
    return p in {"360dialog", "d360", "360"}


def _headers(api_key: str) -> dict[str, str]:
    return {
        "D360-API-KEY": api_key.strip(),
        "Content-Type": "application/json",
    }


def _request(
    method: str,
    path: str,
    api_key: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{D360_BASE}{path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.request(
                method,
                url,
                headers=_headers(api_key),
                json=json_body,
            )
            data = res.json() if res.content else {}
    except Exception as exc:  # noqa: BLE001
        raise WhatsAppCloudError("No pude hablar con 360dialog.") from exc
    if not isinstance(data, dict):
        data = {"raw": data}
    if res.status_code >= 400:
        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        msg = (
            str((err or {}).get("message") or data.get("meta") or data.get("message") or "")
            or f"Error 360dialog HTTP {res.status_code}"
        )
        raise WhatsAppCloudError(msg)
    return data


def probe_api_key(api_key: str) -> dict[str, Any]:
    """Comprueba la key y, si 360dialog lo expone, trae datos del número."""
    info: dict[str, Any] = {}
    try:
        data = _request("GET", "/v1/configs/info", api_key)
        info = data if isinstance(data, dict) else {}
    except WhatsAppCloudError:
        _request("GET", "/v1/configs/webhook", api_key)
    return info


def configure_inbound_webhook(api_key: str) -> None:
    settings = get_settings()
    url = f"{settings.api_public_url.rstrip('/')}/v1/whatsapp/webhook"
    try:
        _request("POST", "/v1/configs/webhook", api_key, json_body={"url": url})
    except WhatsAppCloudError:
        logger.warning("[WA-360] no pude fijar webhook url=%s", url, exc_info=True)


def send_text_d360(*, api_key: str, to: str, body: str) -> dict[str, Any]:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    return _request("POST", "/messages", api_key, json_body=payload)


def send_template_d360(
    *,
    api_key: str,
    to: str,
    template_name: str,
    language: str = "es",
    body_params: list[str] | None = None,
) -> dict[str, Any]:
    template: dict[str, Any] = {
        "name": template_name.strip(),
        "language": {"code": (language or "es").strip() or "es"},
    }
    params = [p.strip() for p in (body_params or []) if str(p).strip()]
    if params:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p[:1024]} for p in params],
            }
        ]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    }
    return _request("POST", "/messages", api_key, json_body=payload)


def list_templates_d360(api_key: str) -> list[dict[str, Any]]:
    try:
        data = _request("GET", "/v1/configs/templates", api_key)
    except WhatsAppCloudError:
        logger.warning("[WA-360] list templates failed", exc_info=True)
        return []
    items = data.get("waba_templates") or data.get("data") or data.get("templates")
    return items if isinstance(items, list) else []


def download_media_d360(api_key: str, media_id: str) -> tuple[bytes, str]:
    meta = _request("GET", f"/{media_id.strip()}", api_key)
    url = str(meta.get("url") or "").strip()
    mime = str(meta.get("mime_type") or "image/jpeg").strip() or "image/jpeg"
    if not url:
        raise WhatsAppCloudError("360dialog: media sin URL.")
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            res = client.get(url, headers={"D360-API-KEY": api_key.strip()})
    except Exception as exc:  # noqa: BLE001
        raise WhatsAppCloudError("No pude descargar la imagen (360dialog).") from exc
    if res.status_code >= 400 or not res.content:
        raise WhatsAppCloudError("Fallo al descargar la imagen (360dialog).")
    return res.content, mime


def parse_channel_fields(info: dict[str, Any]) -> tuple[str, str, str]:
    """phone_number_id, display_phone, verified_name."""
    phone_id = str(
        info.get("phone_number_id")
        or info.get("id")
        or (info.get("settings") or {}).get("phone_number_id")
        or ""
    ).strip()
    display = str(
        info.get("display_phone_number")
        or info.get("display_phone")
        or info.get("phone_number")
        or ""
    ).strip()
    name = str(info.get("verified_name") or info.get("name") or "").strip()
    return phone_id, display, name
