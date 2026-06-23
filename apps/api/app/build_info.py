"""Versión de build — bump en cada deploy crítico (visible en GET /health)."""

from __future__ import annotations

from datetime import datetime, timezone

BUILD_VERSION = "2026-06-23-voice-quality-v42"
BUILD_TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
