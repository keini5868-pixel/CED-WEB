"""Idempotencia de publicaciones Meta — evita doble POST por turno o reintento."""

from __future__ import annotations

import difflib
import re
import threading
import time
import unicodedata

_LOCK = threading.Lock()
_RECENT: dict[str, list[tuple[float, str, str | None]]] = {}
_WINDOW_SEC = 30.0
_SIMILARITY_THRESHOLD = 0.80


def _normalize(text: str) -> str:
    raw = unicodedata.normalize("NFKD", (text or "").lower())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = re.sub(r"[^\w\s]", " ", raw, flags=re.UNICODE)
    return " ".join(raw.split())


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def find_duplicate_publish(user_id: str, message: str, *, platform: str = "facebook") -> str | None:
    """Devuelve post_id previo si hay publicación similar reciente del mismo usuario."""
    uid = (user_id or "").strip()
    norm = _normalize(message)
    if not uid or not norm:
        return None
    key = f"{uid}:{platform}"
    now = time.time()
    with _LOCK:
        rows = _RECENT.get(key, [])
        rows = [(ts, msg, pid) for ts, msg, pid in rows if now - ts <= _WINDOW_SEC]
        _RECENT[key] = rows
        for ts, prev_msg, post_id in reversed(rows):
            if _similarity(norm, prev_msg) >= _SIMILARITY_THRESHOLD:
                return post_id or "dedupe"
    return None


def record_publish(
    user_id: str,
    message: str,
    post_id: str | None,
    *,
    platform: str = "facebook",
) -> None:
    uid = (user_id or "").strip()
    norm = _normalize(message)
    if not uid or not norm:
        return
    key = f"{uid}:{platform}"
    now = time.time()
    with _LOCK:
        rows = [(ts, msg, pid) for ts, msg, pid in _RECENT.get(key, []) if now - ts <= _WINDOW_SEC]
        rows.append((now, norm, post_id))
        _RECENT[key] = rows[-8:]
