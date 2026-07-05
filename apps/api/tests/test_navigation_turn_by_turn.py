"""Tests — navegación turn-by-turn (distancias alineadas con Google Maps UX)."""

from app.services.navigation_voice import (
    ADVANCE_STEP_M,
    ANNOUNCE_DISTANCE_M,
    ARRIVAL_DISTANCE_M,
)


def test_navigation_voice_distance_thresholds():
    assert ANNOUNCE_DISTANCE_M == 200
    assert ADVANCE_STEP_M == 50
    assert ARRIVAL_DISTANCE_M == 50
