from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.hud_health import health_card_lines
from app.services.retell_provider_health import (
    _reset_for_tests,
    classify_retell_error,
    note_create_web_call,
    probe_cheap,
    public_status,
    snapshot,
)


def setup_function() -> None:
    _reset_for_tests()


def test_classify_billing_402() -> None:
    assert classify_retell_error("Error code: 402 - Payment Required trial") == "billing"


def test_classify_auth() -> None:
    assert classify_retell_error("401 Unauthorized") == "auth"


def test_billing_sticks_when_api_retrieve_ok() -> None:
    with patch(
        "app.services.retell_provider_health._schedule_alert",
    ):
        note_create_web_call(ok=False, error=RuntimeError("Error code: 402 Payment Required"))
    assert snapshot()["voice"] == "billing"
    assert public_status()["status"] == "degraded"
    assert public_status()["voice"] == "billing"

    client = MagicMock()
    client.agent.retrieve.return_value = SimpleNamespace(agent_id="agt_1")
    client.voice.list.return_value = SimpleNamespace(voices=[SimpleNamespace(voice_id="v1")])
    settings = SimpleNamespace(
        voice_provider="retell",
        retell_api_key="key",
        retell_agent_id="agt_1",
    )
    with (
        patch("app.services.retell_provider_health._schedule_alert"),
        patch("app.config.get_settings", return_value=settings),
        patch("app.services.retell_client.get_retell_client", return_value=client),
        patch("app.services.retell_agent_cache.get_retell_agent_id", return_value="agt_1"),
    ):
        out = probe_cheap()
    assert out["api_ok"] is True
    assert out["voice"] == "billing"


def test_success_clears_billing() -> None:
    with patch("app.services.retell_provider_health._schedule_alert"):
        note_create_web_call(ok=False, error="402 trial")
        note_create_web_call(ok=True)
    snap = snapshot()
    assert snap["voice"] == "ok"
    assert snap["last_register"] == "ok"
    assert public_status()["status"] == "ok"


def test_hud_lines_voice_saldo() -> None:
    lines = health_card_lines(
        {
            "ok": False,
            "avg_latency_ms": 12,
            "services": {
                "gemini": {"ok": True},
                "supabase_db": {"ok": True},
                "stripe": {"ok": True},
                "voice": {"ok": False, "status": "billing"},
            },
        }
    )
    assert "ALERTA" in lines[0]
    assert lines[2] == "Voz SALDO"
