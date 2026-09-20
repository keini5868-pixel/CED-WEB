"""Almacén local de sellos y wallets — no es la chain."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_WALLETS: dict[str, str] = {}
_SEALS: dict[str, list[dict[str, Any]]] = {}


def bind_wallet(user_id: str, address: str) -> str:
    cleaned = (address or "").strip()
    _WALLETS[user_id] = cleaned
    return cleaned


def get_wallet(user_id: str) -> str:
    return _WALLETS.get(user_id, "")


def add_seal(user_id: str, record: dict[str, Any]) -> dict[str, Any]:
    bucket = _SEALS.setdefault(user_id, [])
    bucket.insert(0, record)
    _SEALS[user_id] = bucket[:80]
    return record


def list_seals(user_id: str) -> list[dict[str, Any]]:
    return list(_SEALS.get(user_id) or [])


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reset_for_tests() -> None:
    _WALLETS.clear()
    _SEALS.clear()
