"""Filtros de la Sala CED — nada de teléfonos, DMs ni reclutamiento."""

from __future__ import annotations

import re

ROOMS = ("prompts", "guiones", "copies", "ayuda")
TOKENS = (
    "saludar",
    "pensar",
    "confundido",
    "ok",
    "celebrar",
    "gracias",
    "idea",
    "video",
    "alto",
    "listo",
)

_PHONE = re.compile(
    r"(?:\+?\d[\d\s.\-]{7,}\d)|(?:\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b)",
    re.I,
)
_EMAIL = re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", re.I)
_HANDLE = re.compile(
    r"\b(?:whatsapp|telegram|t\.me|wa\.me|instagram|ig\s*:|facebook|fb\.com|discord\.gg)\b",
    re.I,
)
_URL = re.compile(r"(https?://[^\s]+)|(\bwww\.[^\s]+)", re.I)
_ALLOWED_HOST = re.compile(
    r"(?:^|://|www\.)(?:youtube\.com|youtu\.be|ced-castillo\.com)(?:/|\b)",
    re.I,
)
_CONTACT = re.compile(
    r"\b(?:te contacto|escr[ií]beme|m[aá]ndame|al privado|dm\b|n[uú]mero\b|celu(?:lar)?\b)\b",
    re.I,
)
_PRICE_SPAM = re.compile(
    r"\b(?:precio de entrada|plan de compensaci[oó]n|paga(?:me|me)|crypto wallet|seed phrase|clave de stripe)\b",
    re.I,
)
_SECRET = re.compile(
    r"\b(?:password|contrase[nñ]a|api[_-]?key|sk_live|sk_test|service_role)\b",
    re.I,
)

MAX_BODY = 1200
MAX_TITLE = 80
POST_COOLDOWN_SEC = 45
REPLY_COOLDOWN_SEC = 15


def normalize_room(room: str) -> str | None:
    value = (room or "").strip().lower()
    return value if value in ROOMS else None


def normalize_token(token: str) -> str | None:
    value = (token or "").strip().lower()
    return value if value in TOKENS else None


def public_display_name(full_name: str | None, email: str | None = None) -> str:
    name = (full_name or "").strip()
    if name:
        return name.split()[0][:24]
    if email and "@" in email:
        return email.split("@", 1)[0][:18]
    return "Operador"


def reject_reason(text: str, *, allow_youtube: bool = True) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return "Escribe algo para publicar."
    if len(raw) > MAX_BODY:
        return f"Máximo {MAX_BODY} caracteres."
    if _PHONE.search(raw):
        return "La Sala no admite números de teléfono."
    if _EMAIL.search(raw):
        return "La Sala no admite correos. Usa el producto, no el privado."
    if _HANDLE.search(raw) or _CONTACT.search(raw):
        return "Sin WhatsApp, Telegram ni ‘te contacto’. La ayuda se queda aquí."
    if _SECRET.search(raw):
        return "No publiques claves ni contraseñas."
    if _PRICE_SPAM.search(raw):
        return "Nada de precios de entrada ni compensación. Eso no se discute aquí."
    for match in _URL.finditer(raw):
        url = match.group(0)
        if allow_youtube and _ALLOWED_HOST.search(url):
            continue
        return "Solo se permiten enlaces de YouTube o ced-castillo.com."
    return None
