"""Identidad CED: expertise marketing/ventas/prospección en los 3 modos."""

from __future__ import annotations

from app.domain.ced_identity import CED_CORE_IDENTITY, CED_MARKETING_EXPERTISE
from app.domain.ced_live_voice_prompt import CED_LIVE_VOICE_SYSTEM_PROMPT
from app.domain.openai_voice_prompt import build_ced_voice_system_prompt
from app.services.advanced_mode.constants import (
    ADVANCED_STREAM_SYSTEM,
    ADVANCED_SYSTEM_PROMPT,
)
from app.services.text_chat import CHAT_SYSTEM_BASE, CHAT_SYSTEM_LIGHT_BASE


def test_core_identity_positions_as_marketing_expert():
    assert "Consultor experto" in CED_CORE_IDENTITY
    assert "marketing digital" in CED_CORE_IDENTITY.lower()
    assert "prospección" in CED_CORE_IDENTITY.lower()
    assert "no solo un ejecutor" in CED_CORE_IDENTITY.lower() or "no solo un ejecutor" in CED_MARKETING_EXPERTISE.lower()


def test_marketing_expertise_block():
    assert "consultor de marketing digital" in CED_MARKETING_EXPERTISE.lower()
    assert "criterio" in CED_MARKETING_EXPERTISE.lower()
    assert "ENTREGA" in CED_MARKETING_EXPERTISE
    assert "texto ≠ imagen" in CED_MARKETING_EXPERTISE or "texto" in CED_MARKETING_EXPERTISE.lower()
    assert "MLM" in CED_MARKETING_EXPERTISE
    assert "red de franquicias" in CED_MARKETING_EXPERTISE.lower()


def test_chat_prompts_include_expertise():
    for prompt in (CHAT_SYSTEM_BASE, CHAT_SYSTEM_LIGHT_BASE):
        assert CED_MARKETING_EXPERTISE in prompt
        assert "MENTOR EN VENTAS" in prompt or "consultor" in prompt.lower()


def test_advanced_prompts_include_expertise():
    assert "consultor" in ADVANCED_SYSTEM_PROMPT.lower()
    assert CED_MARKETING_EXPERTISE in ADVANCED_SYSTEM_PROMPT
    assert CED_MARKETING_EXPERTISE in ADVANCED_STREAM_SYSTEM


def test_voice_prompts_include_expertise():
    live = CED_LIVE_VOICE_SYSTEM_PROMPT
    retell = build_ced_voice_system_prompt()
    assert CED_MARKETING_EXPERTISE in live
    assert CED_MARKETING_EXPERTISE in retell
    assert "prospección" in live.lower() or "prospeccion" in live.lower()
    assert "consultor" in retell.lower()
