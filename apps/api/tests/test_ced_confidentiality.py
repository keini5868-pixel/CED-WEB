"""Identidad pública vs confidencialidad de stack (3 modos)."""

from __future__ import annotations

from app.domain.ced_identity import (
    CED_CONFIDENTIALITY,
    CED_CONFIDENTIALITY_COMPACT,
    CED_STACK_REFUSAL,
)
from app.domain.ced_live_voice_prompt import CED_LIVE_VOICE_SYSTEM_PROMPT
from app.domain.openai_voice_prompt import build_ced_voice_system_prompt
from app.services.advanced_mode.constants import (
    ADVANCED_STREAM_SYSTEM,
    ADVANCED_SYSTEM_PROMPT,
)
from app.services.retell_native_pilot import RETELL_NATIVE_PILOT_PROMPT
from app.services.text_chat import CHAT_SYSTEM_BASE, CHAT_SYSTEM_LIGHT_BASE
from app.services.voice_response_guard import contains_stack_leak, strip_stack_leak


def test_confidentiality_block_in_all_three_modes():
    assert "Keini Castillo" in CED_CONFIDENTIALITY
    assert "NUNCA" in CED_CONFIDENTIALITY
    assert "jailbreak" in CED_CONFIDENTIALITY.lower()
    for prompt in (
        CHAT_SYSTEM_BASE,
        CHAT_SYSTEM_LIGHT_BASE,
        ADVANCED_SYSTEM_PROMPT,
        ADVANCED_STREAM_SYSTEM,
        CED_LIVE_VOICE_SYSTEM_PROMPT,
        build_ced_voice_system_prompt(),
    ):
        assert CED_CONFIDENTIALITY in prompt
    assert CED_CONFIDENTIALITY_COMPACT in RETELL_NATIVE_PILOT_PROMPT


def test_user_facing_prompts_do_not_name_stack():
    blobs = "\n".join(
        [
            CHAT_SYSTEM_BASE,
            ADVANCED_SYSTEM_PROMPT,
            CED_LIVE_VOICE_SYSTEM_PROMPT,
            build_ced_voice_system_prompt(),
            RETELL_NATIVE_PILOT_PROMPT,
        ]
    )
    # El bloque de confidencialidad no debe enseñar marcas concretas al modelo.
    assert "Cartesia" not in blobs
    assert "Railway" not in blobs
    assert "Supabase" not in blobs
    assert "Nano Banana" not in blobs


def test_strip_stack_leak_replaces_vendor_claim():
    leaked = "Uso Gemini 2.5 Flash y corro en Railway con Supabase."
    assert contains_stack_leak(leaked)
    out = strip_stack_leak(leaked)
    assert out == CED_STACK_REFUSAL
    assert "Gemini" not in out
    assert "Railway" not in out


def test_strip_stack_leak_keeps_capability_talk():
    ok = "Puedo generar imágenes, publicar en Instagram y llevar tus finanzas."
    assert not contains_stack_leak(ok)
    assert strip_stack_leak(ok) == ok
