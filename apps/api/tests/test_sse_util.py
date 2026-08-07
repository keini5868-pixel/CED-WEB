"""Tests for SSE text coercion (avoid client-side [object Object])."""

from app.services.sse_util import sse_event


def test_sse_event_keeps_plain_strings():
    out = sse_event("token", {"text": "hola mundo"})
    assert '"text": "hola mundo"' in out or '"text":"hola mundo"' in out


def test_sse_event_coerces_nested_text_object():
    out = sse_event("token", {"text": {"text": "contenido real largo"}})
    assert "contenido real largo" in out
    assert "[object Object]" not in out


def test_sse_event_coerces_content_parts_list():
    out = sse_event(
        "token",
        {"text": [{"type": "text", "text": "parte A"}, {"type": "text", "text": "parte B"}]},
    )
    assert "parte A" in out
    assert "parte B" in out
