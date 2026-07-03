"""Tests — intenciones de navegación por voz y corrección STT."""

from __future__ import annotations

from app.services.navigation_voice_intent import (
    extract_place_query,
    normalize_navigation_query,
    resolve_navigation_place_search,
    resolve_open_map_request,
)
from app.services.retell_llm_types import Utterance


def test_arma_cercano_maps_to_walmart():
    assert normalize_navigation_query("algún arma más cercano") == "Walmart"
    assert extract_place_query("quiero ir a algún arma más cercano") == "Walmart"


def test_resolve_search_from_stt_mishearing():
    req = resolve_navigation_place_search(
        "Ok. Yo quiero ir a algún arma más cercano.",
        [],
    )
    assert req is not None
    assert req["query"] == "Walmart"


def test_confirm_si_after_walmart_question():
    transcript = [
        Utterance(role="agent", content='¿Se refiere a "Walmart", señor?'),
        Utterance(role="user", content="Sí"),
    ]
    req = resolve_navigation_place_search("Sí", transcript)
    assert req is not None
    assert req["query"] == "Walmart"


def test_open_map_phrases():
    assert resolve_open_map_request("¿Activar mapa?") is True
    assert resolve_open_map_request("abre el mapa") is True


def test_walmart_explicit():
    assert extract_place_query("busca Walmart cerca") == "Walmart"
