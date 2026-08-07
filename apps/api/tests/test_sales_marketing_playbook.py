"""Playbook marketing/ventas inyectado en chat, avanzado y voz."""

from __future__ import annotations

from app.domain.ced_identity import CED_MARKETING_EXPERTISE
from app.domain.ced_live_voice_prompt import CED_LIVE_VOICE_SYSTEM_PROMPT
from app.domain.ced_sales_marketing_playbook import (
    CED_SALES_MARKETING_PLAYBOOK,
    append_sales_marketing_playbook_if_needed,
    wants_sales_marketing_playbook,
)
from app.domain.openai_voice_prompt import build_ced_voice_system_prompt
from app.services.advanced_mode.constants import ADVANCED_SYSTEM_PROMPT
from app.services.text_chat import _build_chat_system_light


def test_playbook_has_frameworks_hooks_meta_terminology():
    body = CED_SALES_MARKETING_PLAYBOOK.lower()
    for token in ("aida", "pas", "pastor", "bab", "fab", "acca", "hook", "meta ads"):
        assert token in body
    assert "mlm" in body  # mentioned as forbidden
    assert "red de franquicias" in body
    assert "45–60" in CED_SALES_MARKETING_PLAYBOOK or "45-60" in body
    assert "no menciones" in body or "prohibido listar" in body


def test_wants_playbook_on_copy_and_campaigns():
    assert wants_sales_marketing_playbook("hazme un copy para vender Activise")
    assert wants_sales_marketing_playbook("estructura una campaña de Meta Ads")
    assert wants_sales_marketing_playbook("dame un hook para un Reel")
    assert wants_sales_marketing_playbook("hola cómo estás") is False


def test_terminology_always_in_expertise():
    assert "MLM" in CED_MARKETING_EXPERTISE
    assert "red de franquicias" in CED_MARKETING_EXPERTISE.lower()


def test_chat_light_injects_playbook_for_copy():
    system = _build_chat_system_light("user-test", "escribe un copy PAS para Restorate")
    assert "PLAYBOOK INTERNO" in system
    assert "AIDA" in system


def test_chat_light_skips_playbook_on_greeting():
    system = _build_chat_system_light("user-test", "hola")
    assert "PLAYBOOK INTERNO" not in system


def test_append_idempotent():
    once = append_sales_marketing_playbook_if_needed("BASE", "dame un copy")
    twice = append_sales_marketing_playbook_if_needed(once, "dame un copy")
    assert twice.count("PLAYBOOK INTERNO") == 1


def test_advanced_and_voice_include_playbook():
    assert "PLAYBOOK INTERNO" in ADVANCED_SYSTEM_PROMPT
    assert "PLAYBOOK INTERNO" in CED_LIVE_VOICE_SYSTEM_PROMPT
    assert "PLAYBOOK INTERNO" in build_ced_voice_system_prompt()
