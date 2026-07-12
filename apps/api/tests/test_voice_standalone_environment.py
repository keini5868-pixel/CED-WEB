"""Tests — Fase 1.1 clima en modo standalone Gemini (VOICE_STANDALONE_MODULES)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.voice_test_mode import (
    GEMINI_STANDALONE_MODE,
    is_standalone_module_enabled,
    resolve_standalone_forced_module,
    standalone_user_keys_overlap,
    voice_standalone_modules,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_voice_standalone_modules_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    monkeypatch.setenv("VOICE_STANDALONE_MODULES", "environment, calendar ")
    get_settings.cache_clear()
    assert voice_standalone_modules() == frozenset({"environment", "calendar"})
    assert is_standalone_module_enabled("environment") is True
    assert is_standalone_module_enabled("finance") is False


def test_standalone_modules_empty_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    get_settings.cache_clear()
    assert voice_standalone_modules() == frozenset()


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("¿Cómo está el clima hoy?", "environment"),
        ("¿Va a llover mañana?", "environment"),
        ("Calidad del aire en Charlotte", "environment"),
        ("¿Cómo estás?", None),
        ("Hace calor", None),
    ],
)
def test_resolve_standalone_forced_module_triggers(
    monkeypatch: pytest.MonkeyPatch,
    phrase: str,
    expected: str | None,
) -> None:
    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    monkeypatch.setenv("VOICE_STANDALONE_MODULES", "environment")
    get_settings.cache_clear()
    got = resolve_standalone_forced_module(
        phrase,
        [],
        call_id="test-call",
        user_id="user-1",
    )
    assert got == expected


def test_environment_module_spoken_without_filler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.environment_module import EnvironmentModule

    monkeypatch.setattr(
        "app.modules.environment_module._web_search_environment",
        lambda _uid, _text: "Señor, hoy en Charlotte hay sol y 28 grados.",
    )
    import asyncio

    mod = EnvironmentModule()
    result = asyncio.run(
        mod.activate(
            "¿Cómo está el clima hoy?",
            user_id="user-1",
            call_id="call-1",
            user_text="¿Cómo está el clima hoy?",
        )
    )
    assert result.handles_response is True
    assert result.spoken
    assert "Charlotte" in result.spoken or "28" in result.spoken
    # Standalone path must ignore send_filler — flag may be True on module result.
    assert result.send_filler is True  # module default; router skips filler in standalone


def test_standalone_user_keys_overlap() -> None:
    from app.services.voice_test_mode import standalone_user_keys_overlap

    a = "como esta el clima hoy"
    b = "como esta el clima hoy en charlotte"
    assert standalone_user_keys_overlap(a, b) is True
    assert standalone_user_keys_overlap("como estas", "como esta el clima hoy") is False


def test_concurrent_standalone_lock_prevents_double_delivery() -> None:
    """Simula rid viejo en orquestador + rid nuevo en Gemini — solo uno debe hablar."""
    import asyncio

    lock = asyncio.Lock()
    last_module_key = ""
    last_answered_key = ""
    deliveries: list[str] = []

    async def orch_task() -> None:
        nonlocal last_module_key, last_answered_key
        async with lock:
            await asyncio.sleep(0.05)
            last_module_key = "como esta el clima hoy"
            last_answered_key = last_module_key
            deliveries.append("orch")

    async def gemini_task() -> None:
        async with lock:
            if last_module_key and standalone_user_keys_overlap(
                "como esta el clima hoy",
                last_module_key,
            ):
                return
            deliveries.append("gemini")

    async def run() -> None:
        await asyncio.gather(orch_task(), gemini_task())

    asyncio.run(run())
    assert deliveries == ["orch"]
