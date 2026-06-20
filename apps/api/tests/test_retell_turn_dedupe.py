"""Tests turn-level response_id dedupe helpers (v38 anti-duplication)."""

from app.routers.retell_custom_llm import _is_superseded_turn_rid, _turn_slot


def test_turn_slot_empty_key():
    assert _turn_slot("") == "_empty"
    assert _turn_slot("hola") == "hola"


def test_is_superseded_when_newer_rid_scheduled():
    latest: dict[str, int] = {_turn_slot("qué es la mecánica"): 5}
    superseded, latest_rid = _is_superseded_turn_rid(3, "qué es la mecánica", latest)
    assert superseded is True
    assert latest_rid == 5


def test_not_superseded_when_latest_matches():
    latest: dict[str, int] = {_turn_slot("hola"): 2}
    superseded, latest_rid = _is_superseded_turn_rid(2, "hola", latest)
    assert superseded is False
    assert latest_rid == 2


def test_independent_turn_slots():
    latest: dict[str, int] = {_turn_slot("turno a"): 4}
    superseded, _ = _is_superseded_turn_rid(2, "turno b", latest)
    assert superseded is False
