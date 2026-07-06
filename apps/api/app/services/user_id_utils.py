"""Normalización de user_id — UUID canónico para Supabase."""

from __future__ import annotations

from uuid import UUID


def normalize_user_id(user_id: str) -> str:
    """Convierte cualquier UUID válido al formato canónico (lowercase)."""
    cleaned = str(user_id or "").strip()
    if not cleaned:
        raise ValueError("empty user_id")
    return str(UUID(cleaned))
