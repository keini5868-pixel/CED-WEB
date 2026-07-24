"""Clientes Supabase — anon vs service_role (admin)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_admin_client: Any | None = None


def service_role_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url.strip() and settings.supabase_service_role_key.strip())


def get_supabase_admin(*, require_service_role: bool = False):
    """Cliente service_role (admin)."""
    global _admin_client
    settings = get_settings()
    url = settings.supabase_url.strip()
    service_key = settings.supabase_service_role_key.strip()
    anon_key = settings.supabase_anon_key.strip()

    if not url:
        raise RuntimeError("SUPABASE_URL no configurada")

    from supabase import create_client

    if service_key:
        if _admin_client is None:
            _admin_client = create_client(url, service_key)
        return _admin_client

    if require_service_role:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY requerida para operaciones admin."
        )

    logger.error(
        "[SUPABASE] SUPABASE_SERVICE_ROLE_KEY no configurada — operaciones admin limitadas"
    )
    if anon_key:
        return create_client(url, anon_key)
    raise RuntimeError("Supabase no configurado (falta service_role y anon key)")
