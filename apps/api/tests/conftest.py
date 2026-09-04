"""Pytest — fuerza Gemini en tests para no depender de Ollama local."""

from __future__ import annotations

import os

# Los tests existentes mockean Gemini; el default de producción es llama.
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("RETELL_LLM_PROVIDER", "gemini")

import pytest

from app.config import get_settings

get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _skip_image_art_expander(monkeypatch, request):
    """El expander pega a Gemini con timeout 2s; los tests de pipeline no lo necesitan."""
    if request.node.get_closest_marker("enable_image_expander"):
        return
    monkeypatch.setattr(
        "app.services.image_art_expander.expand_image_scene",
        lambda *args, **kwargs: (None, "skip"),
    )
