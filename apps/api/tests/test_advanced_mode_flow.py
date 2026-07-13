"""Tests — modo avanzado (piloto nativo)."""

from __future__ import annotations

from unittest.mock import patch

from app.services import voice_client_session as vcs
from app.services.advanced_mode_flow import (
    activate_advanced_mode,
    consult_advanced,
    deactivate_advanced_mode,
    is_advanced_activate_phrase,
    is_advanced_deactivate_phrase,
)

USER = "550e8400-e29b-41d4-a716-446655440099"


def setup_function() -> None:
    vcs.set_advanced_mode_active(USER, False)


def test_activation_phrase_strict():
    assert is_advanced_activate_phrase("activa modo avanzado")
    assert is_advanced_activate_phrase("Activa modo avanzado, por favor")
    assert not is_advanced_activate_phrase("modo avanzado")
    assert not is_advanced_activate_phrase("activa la cámara")


def test_deactivate_phrases():
    assert is_advanced_deactivate_phrase("modo normal")
    assert is_advanced_deactivate_phrase("sal del modo avanzado")
    assert is_advanced_deactivate_phrase("desactiva modo avanzado")
    assert not is_advanced_deactivate_phrase("qué tiempo hace")


def test_activate_deactivate_idempotent():
    out = activate_advanced_mode(USER)
    assert out["ok"] is True
    assert out["status"] == "advanced_active"
    assert out["transition"] == "transition_to_advanced_mode_active"
    assert vcs.is_advanced_mode_active(USER)

    again = activate_advanced_mode(USER)
    assert again["status"] == "already_active"
    assert "ya activo" in again["spoken"].lower()

    done = deactivate_advanced_mode(USER)
    assert done["transition"] == "transition_to_general_assistant"
    assert not vcs.is_advanced_mode_active(USER)
    assert "conversacional" in done["spoken"].lower()


def test_consult_requires_active_mode():
    vcs.set_advanced_mode_active(USER, False)
    out = consult_advanced(USER, "explica el interés compuesto")
    assert out["ok"] is False
    assert out["status"] == "not_active"
    assert "activa modo avanzado" in out["spoken"].lower()


def test_consult_available_after_activate_without_retell_transition():
    """Reproduce bug v10: activate OK pero Retell se queda en general_assistant."""
    import asyncio

    from app.services.retell_native_pilot import (
        build_native_pilot_states,
        execute_consult_advanced_tool,
        STATE_GENERAL_ASSISTANT,
    )

    states, _ = build_native_pilot_states(api_public_url="https://api.example.com")
    general = next(s for s in states if s["name"] == STATE_GENERAL_ASSISTANT)
    assert "consult_advanced" in {t["name"] for t in general["tools"]}

    activate_advanced_mode(USER)
    assert vcs.is_advanced_mode_active(USER)

    async def run():
        with patch(
            "app.services.advanced_mode_flow.consultar_sistema_avanzado",
            return_value={"ok": True, "result": "Sócrates y el alquimista comparten búsqueda interior."},
        ):
            return await execute_consult_advanced_tool(
                user_id=USER,
                payload={"call": {"call_id": "c-no-transition"}},
                args={
                    "query": (
                        "análisis de la filosofía de Sócrates comparado con El Alquimista"
                    ),
                },
            )

    out = asyncio.run(run())
    assert out["ok"] is True
    assert "Sócrates" in out["result"] or "alquimista" in out["result"].lower()
    assert "[meta:" not in out["result"]


def test_consult_calls_claude_deep_analysis():
    activate_advanced_mode(USER)
    with patch(
        "app.services.advanced_mode_flow.consultar_sistema_avanzado",
        return_value={
            "ok": True,
            "result": "El interés compuesto reinvierte ganancias para crecer más rápido.",
        },
    ) as mock_c:
        out = consult_advanced(USER, "explica el interés compuesto en simple")
    assert out["ok"] is True
    assert "interés compuesto" in out["spoken"].lower()
    mock_c.assert_called_once()
    assert vcs.get_advanced_last_topic(USER)


def test_consult_deactivate_via_phrase():
    activate_advanced_mode(USER)
    out = consult_advanced(USER, "modo normal")
    assert out["status"] == "advanced_inactive"
    assert not vcs.is_advanced_mode_active(USER)
