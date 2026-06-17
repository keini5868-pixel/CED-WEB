"""Cliente Retell AI — singleton para voz web."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from retell import Retell

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_retell_client() -> Retell | None:
    settings = get_settings()
    api_key = settings.retell_api_key.strip()
    if not api_key:
        return None
    return Retell(api_key=api_key)


def verify_retell_webhook(raw_body: str, signature: str | None) -> bool:
    """Verifica firma X-Retell-Signature de custom functions."""
    client = get_retell_client()
    if not client:
        return False
    if not signature:
        return False
    try:
        return bool(
            client.verify(
                raw_body,
                api_key=get_settings().retell_api_key.strip(),
                signature=signature,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RETELL] verify signature failed: %s", exc)
        return False
