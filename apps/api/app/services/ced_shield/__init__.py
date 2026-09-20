"""CED Shield — spike aislado (Midnight: hash + fecha, sin contenido)."""

from __future__ import annotations

from app.services.ced_shield.gate import ced_shield_enabled, require_ced_shield
from app.services.ced_shield.intents import is_shield_seal_intent

__all__ = [
    "ced_shield_enabled",
    "require_ced_shield",
    "is_shield_seal_intent",
]
