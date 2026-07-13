"""Tests — piloto Retell LLM nativo (get_environment gateway)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.retell_native_pilot import (
    RETELL_NATIVE_PILOT_PROMPT,
    build_get_environment_tool,
    build_native_pilot_tools,
    get_pilot_metrics_snapshot,
    record_tool_metric,
    resolve_environment_tool_query,
)


def test_build_get_environment_tool_has_static_filler():
    tool = build_get_environment_tool(api_public_url="https://api.example.com")
    assert tool["name"] == "get_environment"
    assert tool["execution_message_type"] == "static_text"
    assert "consultando el clima" in tool["execution_message_description"].lower()


def test_build_native_pilot_tools_includes_read_only():
    tools = build_native_pilot_tools(api_public_url="https://api.example.com")
    names = {t["name"] for t in tools}
    assert names == {"get_environment", "list_calendar_events", "read_gmail"}
    for tool in tools:
        assert tool["execution_message_type"] == "static_text"
        assert tool["speak_during_execution"] is True


def test_pilot_prompt_includes_standalone_identity():
    assert "Eres CED" in RETELL_NATIVE_PILOT_PROMPT
    assert "get_environment" in RETELL_NATIVE_PILOT_PROMPT
    assert "ok gracias" in RETELL_NATIVE_PILOT_PROMPT.lower()


def test_resolve_environment_tool_query_prefers_args():
    payload = {"call": {"transcript_object": [{"role": "user", "content": "Charlotte"}]}}
    query = resolve_environment_tool_query(payload, {"query": "clima hoy en Charlotte"})
    assert query == "clima hoy en Charlotte"


def test_resolve_environment_tool_query_falls_back_to_transcript():
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "Hola"},
                {"role": "user", "content": "¿cómo está el clima hoy?"},
            ]
        }
    }
    query = resolve_environment_tool_query(payload, {})
    assert "clima" in query


def test_execute_get_environment_tool_records_latency():
    import asyncio

    from app.services.retell_native_pilot import execute_get_environment_tool

    payload = {
        "call": {"call_id": "call_test_1"},
        "args": {"query": "clima hoy"},
    }

    async def _run():
        with patch(
            "app.modules.environment_module.handle_environment_query_sync",
            return_value={"spoken": "Señor, 24 grados en Charlotte."},
        ):
            return await execute_get_environment_tool(
                user_id="user-1",
                payload=payload,
                args=payload["args"],
            )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert "24 grados" in result["result"]
    assert result["latency_ms"] >= 0
    metrics = get_pilot_metrics_snapshot()
    assert metrics["environment_invocations"] >= 1


def test_get_environment_endpoint_without_user_id():
    client = TestClient(app)
    response = client.post(
        "/v1/retell/tools/get_environment",
        json={"name": "get_environment", "args": {"query": "clima hoy"}},
    )
    # En dev sin RETELL_WEBHOOK_SECRET la firma no se exige; debe degradar sin user_id.
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert "identifiqu" in body["result"].lower() or "usuario" in body["result"].lower()


def test_native_pilot_status_requires_auth():
    client = TestClient(app)
    response = client.get("/v1/retell/native-pilot/status")
    assert response.status_code in {401, 403, 422}


def test_record_tool_metric_rolling_window():
    for idx in range(5):
        record_tool_metric(
            call_id=f"call-{idx}",
            tool_name="get_environment",
            latency_ms=100 + idx,
            ok=True,
            query=f"clima {idx}",
        )
    snap = get_pilot_metrics_snapshot()
    assert snap["get_environment"]["invocations"] >= 5
    assert snap["get_environment"]["avg_latency_ms"] is not None


def test_calendar_read_sync_rejects_create():
    from app.modules.calendar_module import handle_calendar_read_sync

    result = handle_calendar_read_sync("user-1", "agéndame cita mañana a las 3")
    assert "solo puedo consultar" in result["spoken"].lower()


def test_calendar_api_call_refreshes_on_401():
    from app.modules.calendar_module import _calendar_api_call, _handle_calendar_query

    calls = {"n": 0}

    def _fn(access: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.HTTPStatusError(
                "unauthorized",
                request=httpx.Request("GET", "https://google.example/events"),
                response=httpx.Response(401),
            )
        assert access == "fresh-token"
        return "ok"

    with patch(
        "app.modules.calendar_module.get_valid_access_token",
        return_value="stale-token",
    ):
        with patch(
            "app.modules.calendar_module.force_refresh_access_token",
            return_value="fresh-token",
        ):
            assert _calendar_api_call("user-1", _fn) == "ok"
            assert calls["n"] == 2


def test_resolve_calendar_windows_hoy_y_manana():
    from app.modules.calendar_module import _resolve_calendar_windows

    windows = _resolve_calendar_windows("¿qué tengo hoy o eventos de mañana?")
    labels = [label for _, _, label in windows]
    assert labels == ["hoy", "mañana"]


def test_handle_calendar_query_hoy_y_manana_with_events():
    from app.modules.calendar_module import _handle_calendar_query

    with patch(
        "app.modules.calendar_module._calendar_api_call",
        side_effect=lambda _uid, fn: fn("token"),
    ):
        with patch(
            "app.modules.calendar_module.list_events",
            side_effect=[["Hoy 9:00 AM — Standup"], ["Mañana 2:00 PM — Doctor"]],
        ):
            spoken = _handle_calendar_query("user-1", "¿qué tengo hoy o eventos de mañana?")
    assert "Standup" in spoken
    assert "Doctor" in spoken
    assert "hoy" in spoken.lower()
    assert "mañana" in spoken.lower()


def test_gmail_read_sync_rejects_send():
    from app.modules.gmail_module import handle_gmail_read_sync

    result = handle_gmail_read_sync("user-1", "envía un email a juan@test.com")
    assert "solo puedo leer" in result["spoken"].lower()
