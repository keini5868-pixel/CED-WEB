"""Tests: start_drive_navigation usa destino pendiente (no geocodifica «iniciar»)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services.navigation_session import (
    clear_navigation,
    set_place_options,
    update_location,
)
from app.services.voice_tool_executor import (
    _is_nav_confirm_destino,
    _parse_place_option_index,
    execute_voice_tool,
)


def test_parse_option_index_key():
    assert _parse_place_option_index({"option_index": 0}) == 0
    assert _parse_place_option_index({"option_index": "2"}) == 2
    assert _parse_place_option_index({"index": 1}) == 1


def test_is_nav_confirm_destino():
    assert _is_nav_confirm_destino("iniciar")
    assert _is_nav_confirm_destino("sí")
    assert _is_nav_confirm_destino("inicia la navegación")
    assert not _is_nav_confirm_destino("Wells Fargo")
    assert not _is_nav_confirm_destino("downtown charlotte")


def test_start_navigation_confirm_uses_pending_place_not_iniciar_geocode():
    uid = "nav-confirm-pending-user"
    clear_navigation(uid)
    update_location(uid, lat=35.2271, lng=-80.8431, heading=90, speed=0)
    set_place_options(
        uid,
        [
            {
                "name": "Wells Fargo - South Tryon",
                "address": "301 S Tryon St",
                "lat": 35.2255,
                "lng": -80.8432,
            },
            {
                "name": "Wells Fargo Other",
                "address": "Far Away",
                "lat": 35.3,
                "lng": -80.9,
            },
        ],
        query="Wells Fargo",
    )

    fake_route = {
        "ok": True,
        "destination": {
            "lat": 35.2255,
            "lng": -80.8432,
            "label": "Wells Fargo - South Tryon",
        },
        "duration_text": "8 min",
        "distance_text": "1.2 mi",
        "steps": [{"instruction": "Dirígete al sureste"}],
        "path": [{"lat": 35.2271, "lng": -80.8431}, {"lat": 35.2255, "lng": -80.8432}],
    }

    with patch(
        "app.services.voice_tool_executor.compute_route",
        return_value=fake_route,
    ) as mock_route, patch(
        "app.services.voice_tool_executor.geocode_address"
    ) as mock_geo, patch(
        "app.services.voice_tool_executor.search_nearby_places"
    ) as mock_places:

        result = asyncio.run(
            execute_voice_tool(
                "start_navigation",
                uid,
                {"confirm": True, "destino": "iniciar"},
            )
        )

        assert result.get("ok") is True
        assert result.get("client_action") == "begin_navigation"
        assert "Iniciando navegación" in str(result.get("spoken") or "")
        assert "Wells Fargo" in str(result.get("spoken") or "")
        mock_route.assert_called_once()
        assert mock_route.call_args.kwargs["dest_lat"] == 35.2255
        mock_geo.assert_not_called()
        mock_places.assert_not_called()

    clear_navigation(uid)


def test_show_route_preview_then_confirm_begins():
    uid = "nav-preview-then-begin"
    clear_navigation(uid)
    update_location(uid, lat=35.2271, lng=-80.8431)
    set_place_options(
        uid,
        [
            {
                "name": "Downtown Charlotte",
                "address": "Uptown",
                "lat": 35.227,
                "lng": -80.843,
            }
        ],
        query="downtown charlotte",
    )
    fake_route = {
        "ok": True,
        "destination": {"lat": 35.227, "lng": -80.843, "label": "Downtown Charlotte"},
        "duration_text": "5 min",
        "distance_text": "0.8 mi",
        "steps": [],
        "path": [{"lat": 35.2271, "lng": -80.8431}, {"lat": 35.227, "lng": -80.843}],
    }

    with patch(
        "app.services.voice_tool_executor.compute_route",
        return_value=fake_route,
    ):
        preview = asyncio.run(
            execute_voice_tool(
                "start_navigation",
                uid,
                {"option_index": 0},
            )
        )
        assert preview.get("client_action") == "apply_route"
        assert "Iniciando" not in str(preview.get("spoken") or "")

        begun = asyncio.run(
            execute_voice_tool(
                "start_navigation",
                uid,
                {"confirm": True, "destino": "iniciar"},
            )
        )
        assert begun.get("client_action") == "begin_navigation"
        assert "Iniciando navegación" in str(begun.get("spoken") or "")

    clear_navigation(uid)
