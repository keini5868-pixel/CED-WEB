"""Google Gmail API v1 — leer y enviar correos."""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

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


def _decode_body_data(data: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(data + "==")
        return raw.decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        return ""


def _html_to_plain(html: str) -> str:
    text = str(html or "")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(?:p|div|tr|li|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _walk_payload_parts(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Recorre multipart y devuelve fragmentos text/plain y text/html."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        mime = str(node.get("mimeType") or "")
        body_data = (node.get("body") or {}).get("data")
        if body_data:
            decoded = _decode_body_data(str(body_data))
            if decoded:
                if mime == "text/plain":
                    plain_parts.append(decoded)
                elif mime == "text/html":
                    html_parts.append(decoded)
                elif mime.startswith("text/"):
                    plain_parts.append(decoded)
        for part in node.get("parts") or []:
            if isinstance(part, dict):
                walk(part)

    walk(payload)
    return plain_parts, html_parts


def _extract_body_from_payload(payload: dict[str, Any]) -> str:
    plain_parts, html_parts = _walk_payload_parts(payload)
    if plain_parts:
        return "\n\n".join(plain_parts).strip()
    for html in html_parts:
        plain = _html_to_plain(html)
        if plain:
            return plain
    return ""


BodySource = Literal["plain", "html", "snippet", "none"]


@dataclass(frozen=True)
class MessageBodyResult:
    text: str
    source: BodySource
    ok: bool
    snippet: str = ""


def _normalize_compare(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def fetch_message_body_detail(access_token: str, message_id: str) -> MessageBodyResult:
    """Obtiene cuerpo del mensaje con fuente (plain/html/snippet) para diagnóstico."""
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            f"{_GMAIL_BASE}/messages/{message_id}",
            headers=_headers(access_token),
            params={"format": "full"},
        )
        res.raise_for_status()
        data = res.json()

    snippet = str(data.get("snippet") or "").strip()
    payload = data.get("payload") or {}
    plain_parts, html_parts = _walk_payload_parts(payload)
    body = _extract_body_from_payload(payload)

    if body:
        source: BodySource = "html" if html_parts and not plain_parts else "plain"
        logger.info(
            "[GMAIL] body ok msg=%s source=%s len=%s plain_parts=%s html_parts=%s",
            str(message_id)[:12],
            source,
            len(body),
            len(plain_parts),
            len(html_parts),
        )
        return MessageBodyResult(text=body[:4000], source=source, ok=True, snippet=snippet)

    if snippet:
        logger.warning(
            "[GMAIL] body empty msg=%s — fallback snippet len=%s mime=%s",
            str(message_id)[:12],
            len(snippet),
            str(payload.get("mimeType") or ""),
        )
        return MessageBodyResult(text=snippet[:4000], source="snippet", ok=False, snippet=snippet)

    logger.warning(
        "[GMAIL] body unavailable msg=%s mime=%s",
        str(message_id)[:12],
        str(payload.get("mimeType") or ""),
    )
    return MessageBodyResult(text="", source="none", ok=False, snippet=snippet)


def get_message_body(access_token: str, message_id: str) -> str:
    result = fetch_message_body_detail(access_token, message_id)
    if result.ok:
        return result.text
    if result.text:
        return result.text
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
