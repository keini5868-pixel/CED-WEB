"""Tests navegación — Places y helpers de voz."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.navigation_maps import (
    format_distance_imperial,
    search_nearby_places,
    _build_place_row,
    _compute_route_routes_api,
    _search_query_variants,
    _search_via_geocode,
    _search_via_places_legacy,
)
from app.services.voice_tool_executor import _parse_place_option_index


def test_format_distance_imperial_miles():
    assert "mi" in format_distance_imperial(5000)


def test_format_distance_imperial_feet():
    assert "ft" in format_distance_imperial(50)


def test_build_place_row_includes_rich_fields():
    row = _build_place_row(
        name="Walmart",
        address="8322 Pineville Rd",
        lat=35.0,
        lng=-80.8,
        origin_lat=35.1,
        origin_lng=-80.9,
        rating=4.0,
        rating_count=1401,
        phone="+17045551234",
        category="Tienda de alimentación",
        open_now=True,
        hours_text="Cierra a las 11:00 p. m.",
    )
    assert row["rating"] == 4.0
    assert row["rating_count"] == 1401
    assert row["phone"] == "+17045551234"
    assert row["open_now"] is True


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


def test_search_via_places_legacy_sorts_by_distance():
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
        result = _search_via_places_legacy(
            "Walmart",
            origin_lat=35.2271,
            origin_lng=-80.8431,
            limit=3,
            radius_m=50_000,
        )

    assert result["ok"] is True
    places = result["places"]
    assert len(places) == 2
    assert places[0]["name"] == "Walmart Near"
    assert places[0]["distance_text"]


def test_search_nearby_places_falls_back_to_geocode_on_request_denied():
    denied = MagicMock()
    denied.json.return_value = {
        "status": "REQUEST_DENIED",
        "error_message": "This API project is not authorized to use this API.",
    }
    denied_post = MagicMock()
    denied_post.status_code = 403
    denied_post.json.return_value = {
        "error": {"status": "PERMISSION_DENIED", "message": "Places API (New) has not been used"},
    }

    geocode_ok = MagicMock()
    geocode_ok.json.return_value = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "8008 Providence Rd, Charlotte, NC",
                "place_id": "geo1",
                "types": ["establishment", "store"],
                "address_components": [
                    {"long_name": "Walmart", "types": ["establishment"]},
                ],
                "geometry": {"location": {"lat": 35.15, "lng": -80.77}},
            }
        ],
    }

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    def route_request(method, url, **kwargs):
        if method == "post" and "places.googleapis.com" in url:
            return denied_post
        if method == "get" and "place/textsearch" in url:
            return denied
        if method == "get" and "geocode" in url:
            return geocode_ok
        raise AssertionError(f"unexpected request {method} {url}")

    mock_client.post.side_effect = lambda url, **kw: route_request("post", url, **kw)
    mock_client.get.side_effect = lambda url, **kw: route_request("get", url, **kw)

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
    assert result["source"] == "geocode"
    assert len(result["places"]) == 1


def test_search_query_variants_shortens_chain_names():
    variants = _search_query_variants("Walmart Neighborhood Market")
    assert variants[0] == "Walmart Neighborhood Market"
    assert "Walmart" in variants


def test_search_via_geocode_respects_radius():
    geocode_ok = MagicMock()
    geocode_ok.json.return_value = {
        "status": "OK",
        "results": [
            {
                "formatted_address": "Near",
                "place_id": "n",
                "geometry": {"location": {"lat": 35.23, "lng": -80.84}},
            },
            {
                "formatted_address": "Far away",
                "place_id": "f",
                "geometry": {"location": {"lat": 40.0, "lng": -75.0}},
            },
        ],
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = geocode_ok

    with patch("app.services.navigation_maps._maps_key", return_value="test-key"), patch(
        "app.services.navigation_maps.httpx.Client", return_value=mock_client
    ):
        result = _search_via_geocode(
            "Walmart",
            origin_lat=35.2271,
            origin_lng=-80.8431,
            limit=3,
            radius_m=50_000,
        )

    assert result["ok"] is True
    assert len(result["places"]) == 1


def test_compute_route_routes_api_parses_steps():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "routes": [
            {
                "distanceMeters": 16000,
                "duration": "1200s",
                "polyline": {"encodedPolyline": "abc"},
                "legs": [
                    {
                        "distanceMeters": 16000,
                        "duration": "1200s",
                        "localizedValues": {
                            "distance": {"text": "10.0 mi"},
                            "duration": {"text": "20 min"},
                        },
                        "steps": [
                            {
                                "distanceMeters": 300,
                                "staticDuration": "60s",
                                "navigationInstruction": {
                                    "instructions": "Gire a la derecha en Main St"
                                },
                                "startLocation": {
                                    "latLng": {"latitude": 35.22, "longitude": -80.84}
                                },
                                "endLocation": {
                                    "latLng": {"latitude": 35.23, "longitude": -80.83}
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    with patch("app.services.navigation_maps._maps_key", return_value="test-key"), patch(
        "app.services.navigation_maps.decode_polyline", return_value=[{"lat": 35.22, "lng": -80.84}]
    ), patch("app.services.navigation_maps.httpx.Client", return_value=mock_client):
        result = _compute_route_routes_api(
            origin_lat=35.22,
            origin_lng=-80.84,
            dest_lat=35.30,
            dest_lng=-80.80,
            dest_label="Walmart",
        )

    assert result["ok"] is True
    assert result["source"] == "routes_api"
    assert result["steps"][0]["instruction"] == "Gire a la derecha en Main St"
