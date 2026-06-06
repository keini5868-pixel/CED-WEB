"""Health detallado para tarjeta SYSTEM del carrusel HUD."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.services.integrations import (
    check_gemini,
    check_stripe,
    check_supabase,
    check_supabase_auth,
)


def _timed(fn) -> tuple[dict[str, Any], int]:
    start = time.perf_counter()
    result = fn()
    ms = int((time.perf_counter() - start) * 1000)
    return result, ms


def _check_claude() -> dict[str, Any]:
    settings = get_settings()
    key = settings.anthropic_api_key.strip()
    if not key:
        return {"ok": False, "error": "missing_anthropic_api_key"}
    return {"ok": True, "configured": True}


def build_detailed_health() -> dict[str, Any]:
    """Estado agregado + latencias por servicio."""
    supabase_db, supabase_ms = _timed(check_supabase)
    supabase_auth, auth_ms = _timed(check_supabase_auth)
    stripe, stripe_ms = _timed(check_stripe)
    gemini, gemini_ms = _timed(check_gemini)
    claude, claude_ms = _timed(_check_claude)

    services = {
        "gemini": {**gemini, "latency_ms": gemini_ms},
        "supabase_db": {**supabase_db, "latency_ms": supabase_ms},
        "supabase_auth": {**supabase_auth, "latency_ms": auth_ms},
        "stripe": {**stripe, "latency_ms": stripe_ms},
        "claude": {**claude, "latency_ms": claude_ms},
    }

    critical_ok = (
        gemini.get("ok")
        and supabase_db.get("ok")
        and stripe.get("ok")
    )
    latencies = [gemini_ms, supabase_ms, stripe_ms]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

    return {
        "ok": critical_ok,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "avg_latency_ms": avg_latency,
        "services": services,
    }


def health_card_lines(health: dict[str, Any]) -> list[str]:
    avg = health.get("avg_latency_ms", 0)
    status = "OK" if health.get("ok") else "ALERTA"
    services = health.get("services") or {}

    def label(name: str, key: str) -> str:
        svc = services.get(key) or {}
        mark = "OK" if svc.get("ok") else "—"
        return f"{name} {mark}"

    return [
        f"API · {avg} ms · {status}",
        " · ".join(
            [
                label("Gemini", "gemini"),
                label("Supabase", "supabase_db"),
                label("Stripe", "stripe"),
            ],
        ),
    ]
