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


def _decode_body_data(data: str, *, charset: str = "utf-8") -> str:
    try:
        raw = base64.urlsafe_b64decode(data + "==")
    except Exception:  # noqa: BLE001
        return ""
    try:
        enc = (charset or "utf-8").strip().strip('"').lower()
        if enc in {"utf-8", "utf8", "us-ascii", "ascii"}:
            return raw.decode("utf-8", errors="replace").strip()
        return raw.decode(enc, errors="replace").strip()
    except Exception:  # noqa: BLE001
        return raw.decode("utf-8", errors="replace").strip()


def _part_charset(part: dict[str, Any]) -> str:
    for header in part.get("headers") or []:
        if not isinstance(header, dict):
            continue
        if str(header.get("name") or "").lower() != "content-type":
            continue
        value = str(header.get("value") or "")
        match = re.search(r"charset\s*=\s*['\"]?([^;'\"\s]+)", value, re.I)
        if match:
            return match.group(1)
    return "utf-8"


def _fetch_attachment_bytes(
    client: httpx.Client,
    access_token: str,
    message_id: str,
    attachment_id: str,
) -> bytes:
    res = client.get(
        f"{_GMAIL_BASE}/messages/{message_id}/attachments/{attachment_id}",
        headers=_headers(access_token),
    )
    res.raise_for_status()
    data = str(res.json().get("data") or "")
    if not data:
        return b""
    return base64.urlsafe_b64decode(data + "==")


def _ics_to_plain(ics_text: str) -> str:
    """Extrae texto legible de una invitación text/calendar (ICS)."""
    unfolded: list[str] = []
    for raw_line in ics_text.replace("\r\n", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw_line.strip()
        else:
            unfolded.append(raw_line.strip())

    parts: list[str] = []
    for line in unfolded:
        upper = line.upper()
        if upper.startswith("SUMMARY:"):
            parts.append(f"Evento: {line.split(':', 1)[-1].strip()}")
        elif upper.startswith("DESCRIPTION:"):
            desc = line.split(":", 1)[-1].strip()
            desc = desc.replace("\\n", "\n").replace("\\,", ",")
            if desc:
                parts.append(desc)
        elif upper.startswith("LOCATION:"):
            parts.append(f"Lugar: {line.split(':', 1)[-1].strip()}")
        elif upper.startswith("DTSTART"):
            when = line.split(":", 1)[-1].strip()
            if when:
                parts.append(f"Inicio: {when}")
    return "\n".join(parts).strip()


def _summarize_payload_mime(payload: dict[str, Any]) -> str:
    bits: list[str] = []

    def walk(node: dict[str, Any], depth: int = 0) -> None:
        mime = str(node.get("mimeType") or "unknown")
        body = node.get("body") or {}
        has_data = bool(body.get("data"))
        has_attach = bool(body.get("attachmentId"))
        size = int(body.get("size") or 0)
        tag = mime
        if has_data:
            tag += "(inline)"
        elif has_attach:
            tag += f"(attachment:{size}b)"
        bits.append(tag)
        for part in node.get("parts") or []:
            if isinstance(part, dict):
                walk(part, depth + 1)

    walk(payload)
    return " > ".join(bits[:12])


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


def _walk_payload_parts(
    payload: dict[str, Any],
    *,
    client: httpx.Client | None = None,
    access_token: str = "",
    message_id: str = "",
) -> tuple[list[str], list[str], list[str]]:
    """Recorre multipart — plain, html y calendar (ICS)."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    calendar_parts: list[str] = []

    def _decode_part(part: dict[str, Any], mime: str) -> str:
        body_obj = part.get("body") or {}
        body_data = body_obj.get("data")
        charset = _part_charset(part)
        if body_data:
            return _decode_body_data(str(body_data), charset=charset)
        attachment_id = str(body_obj.get("attachmentId") or "")
        if attachment_id and client and access_token and message_id:
            try:
                raw = _fetch_attachment_bytes(client, access_token, message_id, attachment_id)
                if raw:
                    if charset not in {"utf-8", "utf8", "us-ascii", "ascii"}:
                        try:
                            return raw.decode(charset, errors="replace").strip()
                        except Exception:  # noqa: BLE001
                            pass
                    return raw.decode("utf-8", errors="replace").strip()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[GMAIL] attachment fetch failed msg=%s att=%s",
                    message_id[:12],
                    attachment_id[:12],
                )
        return ""

    def walk(node: dict[str, Any]) -> None:
        mime = str(node.get("mimeType") or "")
        decoded = _decode_part(node, mime)
        if decoded:
            if mime == "text/plain":
                plain_parts.append(decoded)
            elif mime == "text/html":
                html_parts.append(decoded)
            elif mime == "text/calendar":
                calendar_parts.append(decoded)
            elif mime.startswith("text/"):
                plain_parts.append(decoded)
        for part in node.get("parts") or []:
            if isinstance(part, dict):
                walk(part)

    walk(payload)
    return plain_parts, html_parts, calendar_parts


_TRIVIAL_PLAIN_MAX_CHARS = 40


def _extract_body_from_payload(
    payload: dict[str, Any],
    *,
    client: httpx.Client | None = None,
    access_token: str = "",
    message_id: str = "",
) -> tuple[str, BodySource]:
    plain_parts, html_parts, calendar_parts = _walk_payload_parts(
        payload,
        client=client,
        access_token=access_token,
        message_id=message_id,
    )
    plain_text = "\n\n".join(plain_parts).strip() if plain_parts else ""
    html_text = ""
    for html in html_parts:
        candidate = _html_to_plain(html)
        if len(candidate) > len(html_text):
            html_text = candidate

    # Promocionales (Alibaba, newsletters): la parte text/plain suele ser trivial
    # («ver en el navegador», un link) mientras el HTML trae el contenido real.
    if plain_text and len(plain_text) >= _TRIVIAL_PLAIN_MAX_CHARS:
        return plain_text, "plain"
    if len(html_text) >= 8 and len(html_text) > len(plain_text):
        return html_text, "html"
    if plain_text:
        return plain_text, "plain"
    for ics in calendar_parts:
        plain = _ics_to_plain(ics)
        if plain:
            return plain, "calendar"
    return "", "none"


def _extract_body_from_raw(
    client: httpx.Client,
    access_token: str,
    message_id: str,
) -> tuple[str, BodySource]:
    """Último recurso: descarga el MIME crudo (format=raw) y lo parsea con la stdlib.

    Cubre estructuras que el walk del format=full no decodifica (charsets raros,
    anidamientos multipart no estándar de correos promocionales).
    """
    import email
    from email import policy

    try:
        res = client.get(
            f"{_GMAIL_BASE}/messages/{message_id}",
            headers=_headers(access_token),
            params={"format": "raw"},
        )
        res.raise_for_status()
        raw_b64 = str(res.json().get("raw") or "")
        if not raw_b64:
            return "", "none"
        msg = email.message_from_bytes(
            base64.urlsafe_b64decode(raw_b64 + "=="),
            policy=policy.default,
        )
        plain_texts: list[str] = []
        html_texts: list[str] = []
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype not in ("text/plain", "text/html"):
                continue
            try:
                content = part.get_content()
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            if ctype == "text/plain":
                plain_texts.append(content.strip())
            else:
                html_texts.append(content)
        plain = "\n\n".join(plain_texts).strip()
        html_plain = ""
        for html in html_texts:
            candidate = _html_to_plain(html)
            if len(candidate) > len(html_plain):
                html_plain = candidate
        if plain and len(plain) >= _TRIVIAL_PLAIN_MAX_CHARS:
            return plain, "plain"
        if len(html_plain) >= 8 and len(html_plain) > len(plain):
            return html_plain, "html"
        if plain:
            return plain, "plain"
    except Exception:  # noqa: BLE001
        logger.warning(
            "[GMAIL] raw fallback failed msg=%s",
            str(message_id)[:12],
        )
    return "", "none"


BodySource = Literal["plain", "html", "calendar", "snippet", "none"]


@dataclass(frozen=True)
class MessageBodyResult:
    text: str
    source: BodySource
    ok: bool
    snippet: str = ""
    mime_summary: str = ""


def _normalize_compare(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def fetch_message_body_detail(access_token: str, message_id: str) -> MessageBodyResult:
    """Obtiene cuerpo del mensaje con fuente (plain/html/calendar/snippet) para diagnóstico."""
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
        mime_summary = _summarize_payload_mime(payload)
        body, source = _extract_body_from_payload(
            payload,
            client=client,
            access_token=access_token,
            message_id=message_id,
        )
        if not body:
            body, source = _extract_body_from_raw(client, access_token, message_id)
            if body:
                logger.info(
                    "[GMAIL] raw fallback ok msg=%s source=%s len=%s",
                    str(message_id)[:12],
                    source,
                    len(body),
                )

    if body:
        logger.info(
            "[GMAIL] body ok msg=%s source=%s len=%s mime=%s",
            str(message_id)[:12],
            source,
            len(body),
            mime_summary[:180],
        )
        return MessageBodyResult(
            text=body[:4000],
            source=source,
            ok=True,
            snippet=snippet,
            mime_summary=mime_summary,
        )

    if snippet:
        logger.warning(
            "[GMAIL] body empty msg=%s source=snippet mime=%s snippet=%r",
            str(message_id)[:12],
            mime_summary[:180],
            snippet[:80],
        )
        return MessageBodyResult(
            text=snippet[:4000],
            source="snippet",
            ok=False,
            snippet=snippet,
            mime_summary=mime_summary,
        )

    logger.warning(
        "[GMAIL] body unavailable msg=%s source=none mime=%s",
        str(message_id)[:12],
        mime_summary[:180],
    )
    return MessageBodyResult(
        text="",
        source="none",
        ok=False,
        snippet=snippet,
        mime_summary=mime_summary,
    )


def get_message_body(access_token: str, message_id: str) -> str:
    result = fetch_message_body_detail(access_token, message_id)
    if result.ok:
        return result.text
    if result.text:
        return result.text
    return "No pude leer el contenido del correo."


def send_message(access_token: str, *, to: str, subject: str, body: str) -> dict[str, Any]:
    from email import policy

    msg = EmailMessage(policy=policy.SMTP)
    msg["To"] = to
    # Subject ASCII-safe vía header encoding estándar (evita MIME roto con acentos).
    msg["Subject"] = subject[:200]
    msg.set_content((body or "")[:8000], charset="utf-8")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    with httpx.Client(timeout=20.0) as client:
        res = client.post(
            f"{_GMAIL_BASE}/messages/send",
            headers=_headers(access_token),
            json={"raw": raw},
        )
        if res.status_code >= 400:
            logger.warning(
                "[GMAIL] send failed status=%s body=%s",
                res.status_code,
                (res.text or "")[:400].replace("\n", " "),
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
