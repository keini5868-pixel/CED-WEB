"""Tests — dedupe de filler y turn handled en voz Retell."""

from app.routers.retell_custom_llm import (
    mark_turn_handled,
    reset_turn_filler_state,
    try_mark_turn_filler_sent,
    turn_already_handled,
)


def test_turn_filler_sent_once_per_turn():
    reset_turn_filler_state("call-1", 7)
    assert try_mark_turn_filler_sent("call-1", 7) is True
    assert try_mark_turn_filler_sent("call-1", 7) is False
    reset_turn_filler_state("call-1", 7)
    assert try_mark_turn_filler_sent("call-1", 7) is True


def test_turn_handled_blocks_duplicate_camera_response():
    mark_turn_handled("call-2", 3)
    assert turn_already_handled("call-2", 3) is True
    assert turn_already_handled("call-2", 4) is False
