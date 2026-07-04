"""Auditoría post-migración 3 capas — módulos y bugs conocidos."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services import voice_client_session as vcs
from app.services.ced_orchestrator import detect_module
from app.services.navigation_session import clear_navigation, update_location
from app.services.retell_llm_types import Utterance
from app.services.voice_llm_common import voice_generation_limits
from app.services.voice_tool_executor import execute_voice_tool


def test_dale_stays_on_active_publish():
    transcript = [
        Utterance(role="agent", content="¿Publico este texto en Instagram, señor?"),
        Utterance(role="user", content="dale"),
    ]
    mod = detect_module("dale", transcript, active_module="publish")
    assert mod == "publish"


def test_dale_stays_on_active_map():
    transcript = [
        Utterance(role="agent", content="Encontré Walmart. ¿Inicio la ruta, señor?"),
        Utterance(role="user", content="dale"),
    ]
    mod = detect_module("dale", transcript, active_module="map")
    assert mod == "map"


def test_web_search_token_budget_for_news():
    max_tokens, timeout = voice_generation_limits("dame las últimas noticias de Venezuela")
    assert max_tokens >= 1536
    assert timeout >= 17.0


def test_map_start_navigation_emits_tool_event():
    uid = "user-audit-map-nav"
    clear_navigation(uid)
    update_location(uid, lat=35.2271, lng=-80.8431)
    vcs.consume_tool_events(uid)

    fake_route = {
        "ok": True,
        "duration_text": "12 min",
        "distance_text": "5 km",
        "destination": {"lat": 35.23, "lng": -80.84, "label": "Walmart"},
        "steps": [{"instruction": "Gire a la derecha"}],
        "path": [[35.2271, -80.8431], [35.23, -80.84]],
    }

    async def run() -> dict:
        with patch(
            "app.services.voice_tool_executor.search_nearby_places",
            return_value={
                "ok": True,
                "places": [
                    {
                        "name": "Walmart",
                        "address": "123 Main",
                        "lat": 35.23,
                        "lng": -80.84,
                    }
                ],
            },
        ):
            await execute_voice_tool(
                "search_nearby_places",
                uid,
                {"query": "Walmart"},
            )
        with patch(
            "app.services.voice_tool_executor.compute_route",
            return_value=fake_route,
        ):
            return await execute_voice_tool(
                "start_navigation",
                uid,
                {"index": 0},
            )

    result = asyncio.run(run())
    assert result.get("ok") is True

    events = vcs.consume_tool_events(uid)
    nav_events = [e for e in events if e.get("type") == "map_start_navigation"]
    assert nav_events, "map_start_navigation tool_event missing"
    last = nav_events[-1]
    assert last.get("destination")
    assert last.get("action") == "apply_route"
    assert last.get("route")


def test_map_search_emits_tool_event():
    uid = "user-audit-map-search"
    clear_navigation(uid)
    update_location(uid, lat=35.2271, lng=-80.8431)
    vcs.consume_tool_events(uid)

    async def run() -> dict:
        with patch(
            "app.services.voice_tool_executor.search_nearby_places",
            return_value={
                "ok": True,
                "places": [
                    {
                        "name": "Walmart",
                        "address": "123 Main",
                        "lat": 35.23,
                        "lng": -80.84,
                    }
                ],
            },
        ):
            return await execute_voice_tool(
                "search_nearby_places",
                uid,
                {"query": "Walmart"},
            )

    result = asyncio.run(run())
    assert result.get("ok") is True
    events = vcs.consume_tool_events(uid)
    search_events = [e for e in events if e.get("type") == "map_search_results"]
    assert search_events
    assert search_events[-1].get("places")
