"""Módulo de viabilidad de producto/servicio (producción).

Kill-switch: VIABILITY_MODULE_ENABLED=false.
No comparte estado de sesión con chat, imagen, prospección ni modo avanzado.
"""

from app.services.viability_pilot.intents import is_viability_module_intent
from app.services.viability_pilot.service import analyze_viability

__all__ = ["analyze_viability", "is_viability_module_intent"]
