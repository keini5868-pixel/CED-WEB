"""Tests — coalescing de parciales de streaming en append_message."""

from __future__ import annotations

from app.services.supabase_db import _should_coalesce_voice_model_message


def test_coalesce_extends_previous_model_message():
    assert _should_coalesce_voice_model_message(
        "Claro, señor.",
        "Claro, señor. Con gusto le contaré a Oliver",
    ) == "update"


def test_coalesce_skips_shorter_partial():
    assert _should_coalesce_voice_model_message(
        "Claro, señor. Con gusto",
        "Claro, señor.",
    ) == "skip"


def test_coalesce_no_match_for_unrelated():
    assert _should_coalesce_voice_model_message(
        "Soy CED.",
        "Soy CED.",
    ) == "skip"


def test_coalesce_skips_exact_duplicate():
    assert _should_coalesce_voice_model_message(
        "Soy CED.",
        "Soy CED.",
    ) == "skip"
