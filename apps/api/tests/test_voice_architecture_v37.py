"""Tests — guard de respuestas y fast-path comentarios."""

from app.services.retell_custom_llm import (
    is_social_comment_read_intent,
    resolve_social_comments_request,
    social_comment_platform,
)
from app.services.voice_response_guard import guard_voice_response


def test_guard_blocks_tool_code_leak():
    blocked_text = 'tool_code print("comentario falso") end_of_tool_code'
    safe, blocked = guard_voice_response(blocked_text)
    assert blocked is True
    assert safe == ""


def test_guard_allows_natural_spanish():
    text = "Señor, hay tres comentarios recientes en Instagram."
    safe, blocked = guard_voice_response(text)
    assert blocked is False
    assert "comentarios" in safe


def test_social_comment_intent_instagram():
    utterance = "Revisa comentarios de Instagram"
    assert is_social_comment_read_intent(utterance) is True
    req = resolve_social_comments_request(utterance)
    assert req is not None
    assert req["platform"] == "instagram"


def test_social_comment_platform_both():
    assert social_comment_platform("revisa comentarios en redes") == "both"
