"""Módulo Análisis de Tendencia (producción).

Kill-switch: TRENDS_MODULE_ENABLED=false.
Aislado de chat público y voz (salvo tool Retell si el kill-switch está ON).
"""

from app.services.trends_pilot.intents import is_trends_module_intent
from app.services.trends_pilot.service import analyze_trends

__all__ = ["analyze_trends", "is_trends_module_intent"]
