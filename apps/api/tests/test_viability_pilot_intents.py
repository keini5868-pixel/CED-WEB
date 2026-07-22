"""Intent de viabilidad — triggers estrictos vs colisiones con otras tools."""

from __future__ import annotations

import pytest

from app.services.chat_intents import (
    is_generate_image_intent,
    is_viability_module_intent,
)
from app.services.viability_pilot.intents import is_viability_module_intent as raw_intent

VIABILITY_YES = [
    "Analiza la viabilidad de mi cafetería de especialidad en Santo Domingo",
    "Quiero un estudio de mercado de mi servicio de limpieza de oficinas",
    "Qué tan viable es mi app de delivery de farmacia",
    "Probabilidad de éxito de mi negocio de panadería artesanal",
    "Hazme un análisis de mercado de mi consultoría de marketing",
    "market viability of my meal prep subscription in Miami",
]

VIABILITY_NO_COLLISIONS = [
    "Genera una imagen de un flyer para mi cafetería",
    "Crea un flyer promocional de mi servicio",
    "Edita la imagen del producto y ponle precio",
    "Publica esto en Instagram",
    "Activa modo avanzado",
    "Busca en internet noticias de startups",
    "Activa la prospección",
    "Busca prospectos en mis comentarios",
    "Reproduce un video de YouTube",
    "Cuánto cuesta el iPhone 16",  # precio suelto → search, no viabilidad
    "Analiza esta imagen",  # visión genérica
    "Investiga el mercado de café",  # advanced/research sin phrasing de viabilidad
]


@pytest.mark.parametrize("text", VIABILITY_YES)
def test_viability_triggers(text: str) -> None:
    assert is_viability_module_intent(text) is True
    assert raw_intent(text) is True


@pytest.mark.parametrize("text", VIABILITY_NO_COLLISIONS)
def test_viability_does_not_steal_other_tools(text: str) -> None:
    assert is_viability_module_intent(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Genera una imagen de un flyer para mi cafetería",
        "Crea un flyer promocional de mi servicio",
    ],
)
def test_image_intent_still_wins_on_flyer_generation(text: str) -> None:
    assert is_generate_image_intent(text) is True
    assert is_viability_module_intent(text) is False
