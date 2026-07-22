"""Módulo piloto — análisis de tendencias de industria.

Solo activo con flag de piloto (header X-CED-Trends-Pilot / env).
Aislado de VIABLE, chat público y voz.
"""

from app.services.trends_pilot.intents import is_trends_module_intent
from app.services.trends_pilot.service import analyze_trends

__all__ = ["analyze_trends", "is_trends_module_intent"]
