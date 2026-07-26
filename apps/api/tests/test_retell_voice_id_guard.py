"""RETELL_VOICE_ID nunca debe resolverse a agent_* (voz mezclada / femenina)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.retell_agent_setup import (
    CED_JARVIS_CUSTOM_VOICE_ID,
    resolve_configured_retell_voice_id,
    resolve_retell_voice_id,
)


def test_agent_id_as_voice_env_uses_agent_custom_voice():
    client = MagicMock()
    with (
        patch(
            "app.services.retell_agent_setup._retrieve_agent_voice_id",
            return_value=CED_JARVIS_CUSTOM_VOICE_ID,
        ),
    ):
        vid = resolve_configured_retell_voice_id(
            client, "agent_b4bab246a2e47aa8ec1f96966d"
        )
    assert vid == CED_JARVIS_CUSTOM_VOICE_ID
    assert not vid.startswith("agent_")


def test_resolve_retell_voice_id_never_returns_agent_prefix():
    with patch(
        "app.services.retell_agent_setup.get_settings",
        return_value=MagicMock(retell_voice_id="agent_xxx"),
    ):
        vid = resolve_retell_voice_id(client=None)
    assert vid == CED_JARVIS_CUSTOM_VOICE_ID
