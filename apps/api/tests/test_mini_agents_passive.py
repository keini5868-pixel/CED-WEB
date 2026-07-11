"""Tests — mini agentes pasivos en orquestador."""

from __future__ import annotations

from app.services.ced_orchestrator import CedOrchestrator, MINI_AGENT_MODULES


def test_orchestrator_preloads_passive_mini_agents() -> None:
    orch = CedOrchestrator(call_id="call-passive-1")
    assert not orch._passive_agents_ready
    orch._ensure_passive_agents()
    assert orch._passive_agents_ready
    for name in MINI_AGENT_MODULES:
        mod = orch._modules[name]
        assert mod.is_passive()
        assert not mod.is_active()


def test_passive_agent_does_not_handle_when_inactive() -> None:
    import asyncio

    from app.modules.camera_module import CameraModule

    mod = CameraModule()
    result = asyncio.run(
        mod.handle_command(
            "activa la cámara",
            user_id="u1",
            call_id="c1",
            user_text="activa la cámara",
        )
    )
    assert result.handles_response is False
