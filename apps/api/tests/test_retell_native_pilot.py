"""Tests — piloto Retell LLM nativo (get_environment gateway)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.retell_native_pilot import (
    RETELL_NATIVE_PILOT_PROMPT,
    build_get_environment_tool,
    get_pilot_metrics_snapshot,
    record_tool_metric,
    resolve_environment_tool_query,
)


def test_build_get_environment_tool_shape():
    tool = build_get_environment_tool(api_public_url="https://api.example.com")
    assert tool["name"] == "get_environment"
    assert tool["type"] == "custom"
    assert tool["url"].endswith("/v1/retell/tools/get_environment")
    assert tool["method"] == "POST"
    assert "query" in tool["parameters"]["properties"]


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
    assert snap["environment_invocations"] >= 5
    assert snap["environment_avg_latency_ms"] is not None
