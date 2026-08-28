"""Módulo Automatización — piloto embudo IG/FB → WhatsApp."""

from app.services.automation_pilot.gate import (
    automation_ig_fb_live_enabled,
    automation_module_enabled,
    require_automation_module,
)
from app.services.automation_pilot.intents import (
    is_automation_config_intent,
    parse_automation_brief,
)

__all__ = [
    "automation_ig_fb_live_enabled",
    "automation_module_enabled",
    "require_automation_module",
    "is_automation_config_intent",
    "parse_automation_brief",
]
