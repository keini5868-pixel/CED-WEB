"""Google Gmail API v1 — leer y enviar correos."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

GmailCategory = Literal["primary", "promotions", "social", "updates", "forums"]

GMAIL_CATEGORY_LABELS: dict[GmailCategory, str] = {
    "primary": "CATEGORY_PERSONAL",
    "promotions": "CATEGORY_PROMOTIONS",
    "social": "CATEGORY_SOCIAL",
    "updates": "CATEGORY_UPDATES",
    "forums": "CATEGORY_FORUMS",
}


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _parse_from_header(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "Desconocido"
    match = re.search(r"^([^<]+)", text)
    if match and "@" not in match.group(1):
        return match.group(1).strip().strip('"')
    match = re.search(r"([^<@]+)@", text)
    if match:
        return match.group(1).strip().strip('"')
    return text.split("@")[0].strip() or text


def format_relative_date(date_header: str) -> str:
    raw = str(date_header or "").strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt.astimezone(timezone.utc)
        minutes = int(delta.total_seconds() // 60)
        if minutes < 1:
            return "Ahora mismo"
        if minutes < 60:
            return f"Hace {minutes} min"
        hours = minutes // 60
        if hours < 24:
            return f"Hace {hours} hora{'s' if hours != 1 else ''}"
        days = hours // 24
        if days == 1:
            return "Hace 1 día"
        if days < 7:
            return f"Hace {days} días"
        return dt.astimezone(timezone.utc).strftime("%d %b")
    except Exception:  # noqa: BLE001
        return raw[:24]


def _fetch_message_metadata(
    client: httpx.Client,
    access_token: str,
    msg_id: str,
) -> dict[str, str]:
    detail = client.get(
        f"{_GMAIL_BASE}/messages/{msg_id}",
        headers=_headers(access_token),
        params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
    )
    detail.raise_for_status()
    payload = detail.json()
    headers = {
        str(h.get("name") or "").lower(): str(h.get("value") or "")
        for h in (payload.get("payload") or {}).get("headers") or []
    }
    from_raw = headers.get("from", "")
    return {
        "id": msg_id,
        "from": from_raw,
        "from_name": _parse_from_header(from_raw),
        "subject": headers.get("subject", "(sin asunto)"),
        "date": headers.get("date", ""),
        "relative_date": format_relative_date(headers.get("date", "")),
        "snippet": str(payload.get("snippet") or "")[:240],
    }


def list_inbox_messages(
    access_token: str,
    *,
    max_results: int = 5,
) -> list[dict[str, str]]:
    """Correos más recientes de la bandeja de entrada (sin filtro de pestaña)."""
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            f"{_GMAIL_BASE}/messages",
            headers=_headers(access_token),
            params={"maxResults": max_results, "labelIds": "INBOX"},
        )
        res.raise_for_status()
        data = res.json()
        ids = [str(m.get("id")) for m in (data.get("messages") or []) if m.get("id")]
        return [
            _fetch_message_metadata(client, access_token, msg_id)
            for msg_id in ids[:max_results]
        ]


def probe_gmail_access(access_token: str) -> bool:
    """Comprueba acceso real a Gmail (no solo tokeninfo)."""
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.get(
                f"{_GMAIL_BASE}/messages",
                headers=_headers(access_token),
                params={"maxResults": 1, "labelIds": "INBOX"},
            )
            return res.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def list_messages(
    access_token: str,
    *,
    query: str = "",
    max_results: int = 5,
) -> list[dict[str, str]]:
    params: dict[str, str | int] = {"maxResults": max_results}
    if query:
        params["q"] = query
    with httpx.Client(timeout=20.0) as client:
        res = client.get(f"{_GMAIL_BASE}/messages", headers=_headers(access_token), params=params)
        res.raise_for_status()
        data = res.json()
        ids = [str(m.get("id")) for m in (data.get("messages") or []) if m.get("id")]
        return [
            _fetch_message_metadata(client, access_token, msg_id)
            for msg_id in ids[:max_results]
        ]


def list_messages_by_category(
    access_token: str,
    category: GmailCategory = "primary",
    *,
    max_results: int = 10,
) -> list[dict[str, str]]:
    label = GMAIL_CATEGORY_LABELS.get(category, GMAIL_CATEGORY_LABELS["primary"])
    params: list[tuple[str, str | int]] = [
        ("maxResults", max_results),
        ("labelIds", "INBOX"),
        ("labelIds", label),
    ]
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            f"{_GMAIL_BASE}/messages",
            headers=_headers(access_token),
            params=params,
        )
        res.raise_for_status()
        data = res.json()
        ids = [str(m.get("id")) for m in (data.get("messages") or []) if m.get("id")]
        return [
            _fetch_message_metadata(client, access_token, msg_id)
            for msg_id in ids[:max_results]
        ]


def get_gmail_emails(user_id: str, category: GmailCategory = "primary") -> dict[str, Any]:
    """Lista emails de una categoría Gmail para HUD / voz."""
    from app.services.google_oauth import get_connection_status, get_valid_access_token

    if not get_connection_status("gmail", user_id).get("connected"):
        return {"connected": False, "category": category, "messages": [], "count": 0}

    try:
        token = get_valid_access_token("gmail", user_id)
        msgs = list_messages_by_category(token, category, max_results=10)
        formatted = [
            {
                "id": m["id"],
                "from": m.get("from_name") or m.get("from", "?"),
                "subject": m.get("subject", "(sin asunto)"),
                "date": m.get("relative_date") or m.get("date", ""),
                "snippet": m.get("snippet", ""),
            }
            for m in msgs
        ]
        return {
            "connected": True,
            "category": category,
            "messages": formatted,
            "count": len(formatted),
        }
    except ValueError as exc:
        if str(exc) == "not_connected":
            return {"connected": False, "category": category, "messages": [], "count": 0}
        raise
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": True,
            "category": category,
            "messages": [],
            "count": 0,
            "error": str(exc)[:200],
        }


def _extract_body_from_payload(payload: dict[str, Any]) -> str:
    mime = str(payload.get("mimeType") or "")
    body_data = (payload.get("body") or {}).get("data")
    if body_data and mime.startswith("text/"):
        try:
            raw = base64.urlsafe_b64decode(body_data + "==")
            return raw.decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            pass

    for part in payload.get("parts") or []:
        part_mime = str(part.get("mimeType") or "")
        if part_mime == "text/plain":
            data = (part.get("body") or {}).get("data")
            if data:
                try:
                    raw = base64.urlsafe_b64decode(data + "==")
                    return raw.decode("utf-8", errors="replace").strip()
                except Exception:  # noqa: BLE001
                    continue
    for part in payload.get("parts") or []:
        nested = _extract_body_from_payload(part)
        if nested:
            return nested
    return ""


def get_message_body(access_token: str, message_id: str) -> str:
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            f"{_GMAIL_BASE}/messages/{message_id}",
            headers=_headers(access_token),
            params={"format": "full"},
        )
        res.raise_for_status()
        data = res.json()
    body = _extract_body_from_payload(data.get("payload") or {})
    if body:
        return body[:4000]
    snippet = str(data.get("snippet") or "").strip()
    if snippet:
        return snippet
    return "No pude leer el contenido del correo."


def send_message(access_token: str, *, to: str, subject: str, body: str) -> dict[str, Any]:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject[:200]
    msg.set_content(body[:8000])
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    with httpx.Client(timeout=20.0) as client:
        res = client.post(
            f"{_GMAIL_BASE}/messages/send",
            headers=_headers(access_token),
            json={"raw": raw},
        )
        res.raise_for_status()
        return res.json()


def extract_sender_query(text: str) -> str:
    match = re.search(
        r"(?:de|del|from)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ0-9._\-@ ]{2,60})",
        text,
        re.I,
    )
    if match:
        return match.group(1).strip()
    match = re.search(
        r"l[eé]e\s+(?:el\s+)?(?:de\s+)?([A-Za-zÁÉÍÓÚáéíóúÑñ0-9._\- ]{2,40})",
        text,
        re.I,
    )
    if match:
        return match.group(1).strip()
    return ""


def extract_recipient(text: str) -> str:
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    if email_match:
        return email_match.group(0)
    match = re.search(
        r"(?:a|para)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ0-9._\- ]{2,40})",
        text,
        re.I,
    )
    return match.group(1).strip() if match else ""


def detect_gmail_category(text: str) -> GmailCategory:
    t = (text or "").lower()
    if re.search(r"promocion|oferta|descuento|marketing", t):
        return "promotions"
    if re.search(r"social|facebook|instagram|twitter", t):
        return "social"
    if re.search(r"actualizacion|banco|recibo|confirmacion", t):
        return "updates"
    if re.search(r"foro|grupo|comunidad", t):
        return "forums"
    return "primary"
