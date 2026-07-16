"""Versión de build — bump en cada deploy crítico (visible en GET /health)."""

from __future__ import annotations

from datetime import datetime, timezone

BUILD_VERSION = "capability-catalog-no-false-publish-v30"
BUILD_TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
