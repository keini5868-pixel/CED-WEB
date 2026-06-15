"""Tests chat multimedia — límites y validación."""

from __future__ import annotations

import pytest

from app.services.chat_intents import is_generate_image_intent, parse_generate_image_prompt
from app.services.chat_multimedia import (
    ALLOWED_IMAGE_TYPES,
    CHAT_DICTATION_DAILY,
    CHAT_VISION_DAILY,
    MAX_AUDIO_BYTES,
    MAX_IMAGE_BYTES,
)


def test_generate_image_intent_keywords():
    assert is_generate_image_intent("Generame una imagen de un castillo digital futurista")
    assert is_generate_image_intent("Necesito una imagen para mi perfil")
    assert is_generate_image_intent("Diseña un creativo para Meta Ads")
    assert parse_generate_image_prompt("Generame una imagen de un castillo digital") == (
        "un castillo digital"
    )


def test_generate_image_intent_rejects_short():
    assert not is_generate_image_intent("hola")


def test_multimedia_limits_configured():
    assert CHAT_DICTATION_DAILY["free_basic"] == 0
    assert CHAT_DICTATION_DAILY["starter"] == 30
    assert CHAT_VISION_DAILY["pro"] == 50
    assert MAX_AUDIO_BYTES == 5 * 1024 * 1024
    assert MAX_IMAGE_BYTES == 5 * 1024 * 1024
    assert "image/jpeg" in ALLOWED_IMAGE_TYPES
