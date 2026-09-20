"""Escritor Midnight — dry-run por defecto. Nunca envía el contenido."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_SUBMIT_TIMEOUT_S = 8.0


def submit_commitment(payload: dict[str, str]) -> dict[str, Any]:
    """Publica solo el compromiso. Si no hay URL, dry-run (no rompe CED)."""
    forbidden = {"content", "body", "transcript", "title", "bytes", "text"}
    if forbidden.intersection(payload.keys()):
        raise ValueError("CED Shield no envía contenido a Midnight.")

    url = (get_settings().ced_shield_midnight_submit_url or "").strip()
    if not url:
        logger.info("[CED-SHIELD] dry-run seal_id=%s", payload.get("seal_id"))
        return {
            "ok": True,
            "mode": "dry_run",
            "submitted": False,
            "tx_ref": f"dry-run:{payload.get('seal_id')}",
        }

    try:
        response = httpx.post(url, json=payload, timeout=_SUBMIT_TIMEOUT_S)
        response.raise_for_status()
        body = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = {}
        tx_ref = str(body.get("tx_ref") or body.get("tx") or body.get("id") or "").strip()
        return {
            "ok": True,
            "mode": "midnight",
            "submitted": True,
            "tx_ref": tx_ref or f"midnight:{payload.get('seal_id')}",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CED-SHIELD] submit failed: %s", exc)
        return {
            "ok": False,
            "mode": "midnight",
            "submitted": False,
            "error": "No pude escribir el sello en Midnight. CED sigue igual.",
        }
