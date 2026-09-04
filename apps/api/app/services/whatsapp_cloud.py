"""WhatsApp Cloud API — token, envío y parseo de webhooks."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
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


def send_text_for_account(
    account: dict[str, Any],
    *,
    to: str,
    body: str,
) -> dict[str, Any]:
    from app.services.whatsapp_360 import is_360dialog, send_text_d360

    token = str(account.get("access_token") or "").strip()
    if is_360dialog(account):
        return send_text_d360(api_key=token, to=to, body=body)
    return send_text_message(
        phone_number_id=str(account.get("phone_number_id") or ""),
        access_token=token,
        to=to,
        body=body,
    )


def send_template_for_account(
    account: dict[str, Any],
    *,
    to: str,
    template_name: str,
    language: str = "es",
    body_params: list[str] | None = None,
) -> dict[str, Any]:
    from app.services.whatsapp_360 import is_360dialog, send_template_d360

    token = str(account.get("access_token") or "").strip()
    if is_360dialog(account):
        return send_template_d360(
            api_key=token,
            to=to,
            template_name=template_name,
            language=language,
            body_params=body_params,
        )
    return send_template_message(
        phone_number_id=str(account.get("phone_number_id") or ""),
        access_token=token,
        to=to,
        template_name=template_name,
        language=language,
        body_params=body_params,
    )


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


def _graph_auth_post(path: str, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{graph_base()}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=30.0) as client:
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
        raise WhatsAppCloudError("No pude hablar con Graph API de WhatsApp.") from exc
    if res.status_code >= 400:
        raise WhatsAppCloudError(
            str((data.get("error") or {}).get("message") or "Error Graph API WhatsApp.")
        )
    return data if isinstance(data, dict) else {}


def _graph_auth_get(path: str, access_token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{graph_base()}/{path.lstrip('/')}"
    q = dict(params or {})
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=q,
            )
            data = res.json() if res.content else {}
    except Exception as exc:  # noqa: BLE001
        raise WhatsAppCloudError("No pude leer Graph API de WhatsApp.") from exc
    if res.status_code >= 400:
        raise WhatsAppCloudError(
            str((data.get("error") or {}).get("message") or "Error Graph API WhatsApp.")
        )
    return data if isinstance(data, dict) else {}


def list_message_templates(waba_id: str, access_token: str) -> list[dict[str, Any]]:
    data = _graph_auth_get(
        f"{waba_id.strip()}/message_templates",
        access_token,
        {"limit": 80, "fields": "name,status,language,category,components"},
    )
    items = data.get("data")
    return items if isinstance(items, list) else []


def create_message_template(
    waba_id: str,
    access_token: str,
    *,
    name: str,
    language: str,
    body: str,
    category: str = "UTILITY",
) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9_]", "_", name.strip().lower())[:512]
    if not slug:
        raise WhatsAppCloudError("Nombre de plantilla no válido.")
    payload = {
        "name": slug,
        "language": (language or "es").strip() or "es",
        "category": (category or "UTILITY").strip().upper(),
        "components": [{"type": "BODY", "text": body.strip()[:1024]}],
    }
    return _graph_auth_post(f"{waba_id.strip()}/message_templates", access_token, payload)


def send_template_message(
    *,
    phone_number_id: str,
    access_token: str,
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
    return _graph_auth_post(f"{phone_number_id}/messages", access_token, payload)


def inbound_message_events(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Texto e imagen del webhook Cloud API / 360dialog."""
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
                wa_from = str(msg.get("from") or "").strip()
                wamid = str(msg.get("id") or "").strip()
                kind = str(msg.get("type") or "").strip().lower()
                if not wa_from or not phone_number_id or not wamid:
                    continue
                if kind == "text":
                    body = str((msg.get("text") or {}).get("body") or "").strip()
                    if not body:
                        continue
                    out.append(
                        {
                            "phone_number_id": phone_number_id,
                            "from": wa_from,
                            "body": body,
                            "wamid": wamid,
                            "kind": "text",
                            "media_id": "",
                            "mime": "",
                        }
                    )
                    continue
                if kind == "image":
                    image = msg.get("image") if isinstance(msg.get("image"), dict) else {}
                    media_id = str(image.get("id") or "").strip()
                    caption = str(image.get("caption") or "").strip()
                    mime = str(image.get("mime_type") or "image/jpeg").strip()
                    out.append(
                        {
                            "phone_number_id": phone_number_id,
                            "from": wa_from,
                            "body": caption or "(imagen)",
                            "wamid": wamid,
                            "kind": "image",
                            "media_id": media_id,
                            "mime": mime or "image/jpeg",
                        }
                    )
    return out


def inbound_text_events(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Solo texto — compatibilidad de tests."""
    return [e for e in inbound_message_events(payload) if e.get("kind") == "text"]


def download_graph_media(media_id: str, access_token: str) -> tuple[bytes, str]:
    meta = _graph_auth_get(media_id.strip(), access_token)
    url = str(meta.get("url") or "").strip()
    mime = str(meta.get("mime_type") or "image/jpeg").strip() or "image/jpeg"
    if not url:
        raise WhatsAppCloudError("Media WhatsApp sin URL.")
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            res = client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    except Exception as exc:  # noqa: BLE001
        raise WhatsAppCloudError("No pude descargar la imagen de WhatsApp.") from exc
    if res.status_code >= 400 or not res.content:
        raise WhatsAppCloudError("Fallo al descargar la imagen de WhatsApp.")
    return res.content, mime


def download_media_for_account(account: dict[str, Any], media_id: str) -> tuple[bytes, str]:
    mid = (media_id or "").strip()
    if not mid:
        raise WhatsAppCloudError("Falta media_id.")
    from app.services.whatsapp_360 import download_media_d360, is_360dialog

    token = str(account.get("access_token") or "").strip()
    if is_360dialog(account):
        return download_media_d360(token, mid)
    return download_graph_media(mid, token)
