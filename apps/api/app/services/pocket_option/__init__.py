"""Módulo experimental Pocket Option (demo, solo admin).

Kill-switch: POCKET_OPTION_MODULE_ENABLED=false (default).
No expuesto a usuarios CED ni a planes/precios.
"""

from app.services.pocket_option.gate import (
    pocket_option_module_enabled,
    require_pocket_option_module_enabled,
)

__all__ = [
    "pocket_option_module_enabled",
    "require_pocket_option_module_enabled",
]
