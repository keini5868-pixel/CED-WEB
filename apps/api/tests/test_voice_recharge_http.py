"""Prueba extremo a extremo (HTTP real) — recarga necesitada en voz.

Simula el flujo real que usa el frontend: `useCedVoiceSession` hace poll a
`GET /v1/voice/client-state`. Aquí ejecutamos la tool de voz real
(`execute_voice_tool`) para un usuario sin plan/saldo y luego confirmamos,
a través del mismo endpoint HTTP que consume el navegador, que el
`client_action` "recharge_needed" queda disponible para abrir el modal —
el mismo canal ya usado y verificado para el panel de YouTube.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app
from app.services import voice_client_session as vcs
from app.services.voice_tool_executor import execute_voice_tool

SAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440099"


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID
    return TestClient(app)


def test_voice_client_state_http_surfaces_recharge_needed_for_image():
    vcs.consume_client_action(SAMPLE_UUID)
    client = _client()
    try:
        with patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={
                "ok": False,
                "url": None,
                "error": "Alcanzaste el límite de imágenes. Recarga desde $10 para continuar.",
                "code": "needs_recharge",
            },
        ), patch(
            "app.services.voice_tool_executor.voice_access_state",
            return_value={"plan_id": "free_basic"},
        ):
            tool_result = asyncio.run(
                execute_voice_tool(
                    "generate_image", SAMPLE_UUID, {"prompt": "un gato astronauta"}
                )
            )
        assert tool_result["ok"] is False
        assert tool_result["error"] == "needs_recharge"

        res = client.get(
            "/v1/voice/client-state",
            headers={"Authorization": "Bearer test"},
        )
        assert res.status_code == 200
        data = res.json()
        action = data.get("client_action")
        assert action is not None, data
        assert action["action"] == "recharge_needed"
        assert action["payload"]["resource"] == "image"

        events = data.get("tool_events") or []
        assert any(
            ev.get("type") == "recharge_needed" and ev.get("resource") == "image"
            for ev in events
        )
    finally:
        client.app.dependency_overrides.clear()
        vcs.consume_client_action(SAMPLE_UUID)


def test_voice_client_state_http_surfaces_recharge_needed_for_pdf():
    from types import SimpleNamespace

    vcs.consume_client_action(SAMPLE_UUID)
    client = _client()
    try:
        with patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(SimpleNamespace(pdf_reports=False), "ok", False),
        ), patch("app.services.wallet.can_afford", return_value=False):
            tool_result = asyncio.run(
                execute_voice_tool(
                    "generar_pdf",
                    SAMPLE_UUID,
                    {"titulo": "Reporte", "contenido": "Contenido de prueba largo suficiente."},
                )
            )
        assert tool_result["ok"] is False
        assert tool_result["error"] == "needs_recharge"

        res = client.get(
            "/v1/voice/client-state",
            headers={"Authorization": "Bearer test"},
        )
        assert res.status_code == 200
        data = res.json()
        action = data.get("client_action")
        assert action is not None, data
        assert action["action"] == "recharge_needed"
        assert action["payload"]["resource"] == "pdf"
    finally:
        client.app.dependency_overrides.clear()
        vcs.consume_client_action(SAMPLE_UUID)
