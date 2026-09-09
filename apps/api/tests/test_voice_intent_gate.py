"""Tests — clasificación local voice_intent_gate (sin LLM)."""

from __future__ import annotations

import pytest

from app.services.voice_intent_gate import (
    detect_local_module_hints,
    has_explicit_module_signal,
    should_run_orchestrator,
)


@pytest.mark.parametrize(
    ("phrase", "expect_signal"),
    [
        ("¿Qué es el marketing digital?", False),
        ("Cuéntame sobre inteligencia artificial", False),
        ("Explícame la teoría de la relatividad", False),
        ("Gracias por tu ayuda", False),
        ("Hola, ¿cómo estás?", False),
        ("Me siento cansado hoy", False),
        ("¿Cuál es la capital de Francia?", False),
        ("Lee mi último correo de Gmail", False),
        ("Agéndame una cita mañana a las 3", False),
        ("Guárdame en finanzas que gasté 50 dólares", True),
        ("Activa la cámara y dime qué ves", True),
        ("Llévame al aeropuerto en modo conducir", True),
        ("Publica esto en Instagram", True),
        ("Genera un PDF con el resumen", True),
        ("Crea una imagen de un logo moderno", True),
        ("Activa modo prospección en Facebook", True),
        ("Abre el modo avanzado con Claude", True),
        ("¿Qué clima hace hoy?", True),
        ("Ayúdame con un mensaje de prospección para FitLine", False),
        ("Dame ideas de prospección para FitLine", False),
    ],
)
def test_has_explicit_module_signal(phrase: str, expect_signal: bool) -> None:
    assert has_explicit_module_signal(phrase) is expect_signal


@pytest.mark.parametrize(
    ("phrase", "expected_module"),
    [
        ("Registra un gasto de 20 en finanzas", "finance"),
        ("Activa la cámara", "camera"),
        ("Navega al mall más cercano", "map"),
        ("Publica en Facebook", "publish"),
        ("Genera un PDF", "pdf"),
        ("Crea una imagen", "image_gen"),
        ("Modo prospección comentarios Instagram", "prospection"),
        ("Modo avanzado Claude", "advanced"),
    ],
)
def test_detect_local_module_hints(phrase: str, expected_module: str) -> None:
    hints = detect_local_module_hints(phrase)
    assert expected_module in hints


def test_should_run_orchestrator_general_knowledge_bypass() -> None:
    phrase = "¿Qué es el marketing digital?"
    assert should_run_orchestrator(phrase, active_module=None, forced_module=None) is False


def test_should_run_orchestrator_when_module_active() -> None:
    assert should_run_orchestrator("hola", active_module="map", forced_module=None) is True


def test_should_run_orchestrator_strict_forced() -> None:
    assert should_run_orchestrator("hola", active_module=None, forced_module="pdf") is True


def test_should_run_orchestrator_explicit_signal() -> None:
    assert should_run_orchestrator("consulta mis finanzas", active_module=None, forced_module=None) is True
