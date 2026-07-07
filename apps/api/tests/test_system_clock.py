"""Tests — reloj autoritativo del servidor."""

from __future__ import annotations

from app.services.system_clock import (
    clock_context_block,
    format_datetime_mx,
    try_instant_datetime_reply,
)


def test_instant_datetime_direct_query():
    reply = try_instant_datetime_reply("qué día es hoy")
    assert reply
    assert "Hoy es" in reply
    assert "2024" not in reply


def test_instant_datetime_confirmation_after_prior_question():
    history = [
        {"role": "user", "content": "qué día es hoy"},
        {"role": "assistant", "content": "Hoy es jueves 23 de mayo de 2024, señor."},
    ]
    reply = try_instant_datetime_reply("estás seguro", history=history)
    assert reply
    assert "Hoy es" in reply
    assert "2024" not in reply


def test_clock_context_block_has_authoritative_marker():
    block = clock_context_block()
    assert "RELOJ DEL SERVIDOR" in block
    assert "NO inventes" in block


def test_format_datetime_mx_includes_time():
    reply = format_datetime_mx()
    assert "Ciudad de México" in reply
    assert ":" in reply
