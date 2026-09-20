"""Hash local — el contenido nunca viaja a Midnight."""

from __future__ import annotations

import hashlib
import re

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_content_sha256(value: str) -> str | None:
    hex_digest = (value or "").strip().lower()
    if not _SHA256_HEX.fullmatch(hex_digest):
        return None
    return hex_digest


def on_chain_payload(
    *,
    content_sha256: str,
    sealed_at: str,
    wallet: str,
    kind: str,
    seal_id: str,
) -> dict[str, str]:
    """Único JSON que puede salir hacia Midnight: sin cuerpo, título ni transcript."""
    return {
        "schema": "ced-shield-v1",
        "seal_id": seal_id,
        "kind": kind,
        "content_sha256": content_sha256,
        "sealed_at": sealed_at,
        "wallet": wallet,
    }
