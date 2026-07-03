"""Tests — intenciones de navegación por voz y corrección STT."""

from __future__ import annotations

from app.services.cognitive_intents import is_navigation_confirm
from app.services.navigation_voice_intent import (
    extract_place_query,
    normalize_navigation_query,
    resolve_navigation_confirm,
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


def test_is_navigation_confirm_phrases():
    assert is_navigation_confirm("sí")
    assert is_navigation_confirm("dale")
    assert is_navigation_confirm("vamos")
    assert is_navigation_confirm("el primero")
    assert not is_navigation_confirm("busca walmart cerca")


def test_resolve_navigation_confirm_after_place_search():
    from app.services.navigation_session import set_place_options

    uid = "test-nav-confirm-user"
    places = [
        {
            "name": "Walmart Supercenter",
            "lat": 18.45,
            "lng": -69.95,
            "address": "Av. Winston Churchill",
            "distance_text": "1.2 km",
        }
    ]
    set_place_options(uid, places, query="Walmart")
    transcript = [
        Utterance(
            role="agent",
            content="Señor, encontré un Walmart cercano. ¿Inicio el viaje?",
        ),
        Utterance(role="user", content="Sí"),
    ]
    req = resolve_navigation_confirm("Sí", transcript, user_id=uid)
    assert req is not None
    assert req["action"] == "start_navigation"
    assert req["index"] == 0
    assert req["destination"]["name"] == "Walmart Supercenter"


def test_resolve_navigation_confirm_begin_when_route_ready():
    from app.services.navigation_session import clear_navigation, set_route

    uid = "test-nav-begin-user"
    clear_navigation(uid)
    set_route(
        uid,
        {
            "ok": True,
            "destination": {"label": "Walmart"},
            "duration_text": "5 min",
            "steps": [{"instruction": "Gire a la derecha"}],
        },
    )
    transcript = [
        Utterance(role="agent", content="Ruta lista. ¿Iniciamos?"),
        Utterance(role="user", content="dale"),
    ]
    req = resolve_navigation_confirm("dale", transcript, user_id=uid)
    assert req is not None
    assert req["action"] == "begin_navigation"
