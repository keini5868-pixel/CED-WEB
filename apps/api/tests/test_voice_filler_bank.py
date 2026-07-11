"""Tests — banco de fillers de voz y rotación."""

from __future__ import annotations

from app.services.voice_filler_bank import pick_voice_filler, reset_filler_rotation


def test_filler_rotation_avoids_immediate_repeat() -> None:
    call_id = "call-filler-rot"
    reset_filler_rotation(call_id)
    first = pick_voice_filler("general", call_id=call_id)
    second = pick_voice_filler("general", call_id=call_id)
    assert first != second


def test_module_filler_category() -> None:
    call_id = "call-filler-mod"
    reset_filler_rotation(call_id)
    phrase = pick_voice_filler("module", call_id=call_id, module="gmail")
    assert "señor" in phrase.lower()
    assert "correo" in phrase.lower() or "gmail" in phrase.lower() or "bandeja" in phrase.lower()


def test_web_search_filler_pool() -> None:
    call_id = "call-filler-web"
    reset_filler_rotation(call_id)
    seen: set[str] = set()
    for _ in range(5):
        seen.add(pick_voice_filler("web_search", call_id=call_id))
    assert len(seen) >= 3


def test_ten_conversation_filler_categories_distinct() -> None:
    """Simula 10 turnos variados — categorías correctas y sin repetir seguido."""
    call_id = "call-ten-turns"
    reset_filler_rotation(call_id)
    scenarios = [
        ("general", None),
        ("general", None),
        ("web_search", None),
        ("module", "gmail"),
        ("module", "calendar"),
        ("module", "finance"),
        ("module", "map"),
        ("module", "camera"),
        ("module", "pdf"),
        ("general", None),
    ]
    prev = ""
    for category, module in scenarios:
        phrase = pick_voice_filler(category, call_id=call_id, module=module)
        assert "señor" in phrase.lower()
        assert phrase != prev
        prev = phrase
