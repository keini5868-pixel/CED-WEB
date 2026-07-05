"""Tests — módulo ambiente (búsqueda web)."""

from __future__ import annotations

from unittest.mock import patch

from app.modules.environment_module import (
    build_environment_search_query,
    handle_environment_query_sync,
    is_environment_intent,
    resolve_environment_place,
)
from app.services.ced_orchestrator import detect_module, detect_module_from_patterns


def test_is_environment_intent():
    assert is_environment_intent("¿qué clima hay hoy?")
    assert is_environment_intent("¿cómo está la calidad del aire?")
    assert is_environment_intent("¿hay mucho polen hoy?")
    assert not is_environment_intent("hola")


def test_orchestrator_detects_environment_module():
    assert detect_module_from_patterns("¿qué clima hay hoy?") == "environment"
    mod = detect_module("¿cómo está la calidad del aire?", [])
    assert mod == "environment"


def test_build_environment_search_query_defaults_charlotte():
    query = build_environment_search_query("user-1", "¿qué clima hay hoy?")
    assert query == "clima Charlotte NC hoy"


def test_build_environment_search_query_with_place():
    query = build_environment_search_query("user-1", "clima en Miami")
    assert "Miami" in query


def test_resolve_environment_place_from_query():
    place = resolve_environment_place("user-1", "temperatura en Raleigh")
    assert place == "Raleigh"


def test_handle_environment_query_sync_uses_web_search():
    with patch(
        "app.services.gemini_grounded.execute_search_web_sync",
        return_value={"ok": True, "summary": "28°C, cielo despejado."},
    ):
        result = handle_environment_query_sync("user-1", "¿qué clima hay hoy?")
    assert "28" in result["spoken"]
