"""Tests — orquestador 3 capas."""

from app.services.ced_orchestrator import (
    detect_module,
    detect_module_from_patterns,
    get_context_overlay,
    ced_orchestrator,
)
from app.services.retell_llm_types import Utterance


def test_detect_map_open():
    mod = detect_module("abre el mapa", [])
    assert mod == "map"


def test_detect_web_search_patterns():
    assert detect_module_from_patterns("noticias de Venezuela") == "web_search"
    mod = detect_module("noticias de Venezuela hoy", [])
    assert mod == "web_search"


def test_detect_image_gen():
    mod = detect_module("genera una imagen de Charlotte", [])
    assert mod == "image_gen"


def test_dale_stays_on_active_map():
    transcript = [
        Utterance(role="agent", content="Encontré Walmart. ¿Inicio la ruta, señor?"),
        Utterance(role="user", content="dale"),
    ]
    mod = detect_module("dale", transcript, active_module="map")
    assert mod == "map"


def test_context_overlay_map():
    overlay = get_context_overlay("map")
    assert overlay and "NAVEGACIÓN" in overlay.upper()


def test_ced_orchestrator_singleton():
    orch_a = ced_orchestrator.get("call-test-1")
    orch_b = ced_orchestrator.get("call-test-1")
    assert orch_a is orch_b
