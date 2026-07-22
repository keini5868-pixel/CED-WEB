"""Piloto módulo Oportunidades — catálogo de oportunidades de negocio.

Solo activo con flag de piloto (header X-CED-Opportunities-Pilot / env).
"""

from __future__ import annotations

from app.services.opportunities_pilot.service import (
    get_opportunity_detail,
    list_opportunity_catalog,
)

__all__ = ["get_opportunity_detail", "list_opportunity_catalog"]
