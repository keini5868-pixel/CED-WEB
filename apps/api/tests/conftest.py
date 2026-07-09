"""Pytest — fuerza Gemini en tests para no depender de Ollama local."""

from __future__ import annotations

import os

# Los tests existentes mockean Gemini; el default de producción es llama.
os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("RETELL_LLM_PROVIDER", "gemini")

from app.config import get_settings

get_settings.cache_clear()
