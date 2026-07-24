"""Snapshot de estado para el panel admin (solo lectura)."""

from __future__ import annotations

from app.config import get_settings
from app.services.pocket_option.gate import pocket_option_module_enabled
from app.services.pocket_option import store


def status_snapshot() -> dict:
    settings = get_settings()
    st = store.get_status()
    data = st.to_dict()
    data["enabled"] = pocket_option_module_enabled()
    data["ssid_configured"] = bool(settings.pocket_option_ssid.strip())
    data["amount"] = settings.pocket_option_amount
    data["expiry_seconds"] = settings.pocket_option_expiry_seconds
    # Nunca exponer el SSID
    return data
