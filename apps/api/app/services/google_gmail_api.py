"""Google Gmail API v1 — leer y enviar correos."""

from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from typing import Any

import httpx

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


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
        results: list[dict[str, str]] = []
        for msg_id in ids[:max_results]:
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
            results.append(
                {
                    "id": msg_id,
                    "from": headers.get("from", ""),
                    "subject": headers.get("subject", "(sin asunto)"),
                    "date": headers.get("date", ""),
                    "snippet": str(payload.get("snippet") or "")[:240],
                }
            )
    return results


def get_message_body(access_token: str, message_id: str) -> str:
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            f"{_GMAIL_BASE}/messages/{message_id}",
            headers=_headers(access_token),
            params={"format": "full"},
        )
        res.raise_for_status()
        data = res.json()
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
