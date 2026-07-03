"""Tests navegación — Places y helpers de voz."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.navigation_maps import format_distance_imperial, search_nearby_places
from app.services.voice_tool_executor import _parse_place_option_index


def test_format_distance_imperial_miles():
    assert "mi" in format_distance_imperial(5000)


def test_format_distance_imperial_feet():
    assert "ft" in format_distance_imperial(50)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"opcion": "el primero"}, 0),
        ({"opcion": "segundo"}, 1),
        ({"index": 2}, 2),
        ({"destino": "vamos al más cercano"}, 0),
        ({}, None),
    ],
)
def test_parse_place_option_index(params, expected):
    assert _parse_place_option_index(params) == expected


def test_search_nearby_places_sorts_by_distance():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "OK",
        "results": [
            {
                "name": "Walmart Far",
                "formatted_address": "Far Rd",
                "place_id": "a",
                "geometry": {"location": {"lat": 35.3, "lng": -80.8}},
            },
            {
                "name": "Walmart Near",
                "formatted_address": "Near Rd",
                "place_id": "b",
                "geometry": {"location": {"lat": 35.25, "lng": -80.75}},
            },
        ],
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch("app.services.navigation_maps._maps_key", return_value="test-key"), patch(
        "app.services.navigation_maps.httpx.Client", return_value=mock_client
    ):
        result = search_nearby_places(
            "Walmart",
            origin_lat=35.2271,
            origin_lng=-80.8431,
            limit=3,
        )

    assert result["ok"] is True
    places = result["places"]
    assert len(places) == 2
    assert places[0]["name"] == "Walmart Near"
    assert places[0]["distance_text"]
