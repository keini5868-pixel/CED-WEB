"""Módulo Oportunidades — producción (catálogo de oportunidades de negocio).

Kill-switch: OPPORTUNITIES_MODULE_ENABLED=false.
"""

from __future__ import annotations

from app.services.opportunities_pilot.service import (
    get_opportunity_detail,
    list_opportunity_catalog,
)

__all__ = ["get_opportunity_detail", "list_opportunity_catalog"]
