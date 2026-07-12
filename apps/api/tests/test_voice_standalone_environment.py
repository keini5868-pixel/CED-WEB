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
        ("dame informacion de la calidad de aire", "environment"),
        ("informacion sobre la calidad del aire", "environment"),
        ("Dame informacion sobre el clima el dia de hoy", "environment"),
        ("dame informacion sobre el clima hoy", "environment"),
        ("calidad de aire", "environment"),
        ("informacion sobre el clima", "environment"),
        ("¿Cómo estás?", None),
        ("Hace calor", None),
        ("hablamos del clima ayer", None),
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


def test_environment_location_followup_after_air_quality_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.retell_llm_types import Utterance

    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    monkeypatch.setenv("VOICE_STANDALONE_MODULES", "environment")
    get_settings.cache_clear()

    transcript = [
        Utterance(role="user", content="dame informacion de la calidad de aire"),
        Utterance(
            role="agent",
            content="¿Tiene alguna ubicación específica en mente, señor?",
        ),
    ]
    got = resolve_standalone_forced_module(
        "Charlotte",
        transcript,
        call_id="test-call",
        user_id="user-1",
    )
    assert got == "environment"


def test_compose_environment_query_merges_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.environment_module import compose_environment_query
    from app.services.retell_llm_types import Utterance

    transcript = [
        Utterance(role="user", content="dame informacion de la calidad de aire"),
        Utterance(role="agent", content="¿Dónde, señor?"),
    ]
    merged = compose_environment_query("Carolina del Norte", transcript)
    assert "calidad" in merged.lower()
    assert "Carolina del Norte" in merged


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("dame informacion sobre el clima hoy", True),
        ("calidad de aire", True),
        ("informacion del tiempo", True),
        ("Hace calor", False),
        ("hablamos del clima ayer", False),
        ("me gusta el clima de colombia", False),
        ("como estas", False),
    ],
)
def test_is_environment_action_request(phrase: str, expected: bool) -> None:
    from app.modules.environment_module import is_environment_action_request

    assert is_environment_action_request(phrase) is expected


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Charlotte", True),
        ("Carolina del Norte", True),
        ("Miami", True),
        ("ok gracias", False),
        ("estas ahi", False),
        ("¿Estás ahí?", False),
        ("gracias", False),
        ("si me escuchas", False),
        ("Sí, me escuchas", False),
    ],
)
def test_is_environment_location_followup(phrase: str, expected: bool) -> None:
    from app.modules.environment_module import is_environment_location_followup

    assert is_environment_location_followup(phrase) is expected


def test_casual_turn_after_weather_does_not_force_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduce bug r5: clima OK → «ok gracias» debe ir a charla, no al módulo."""
    from app.services.retell_llm_types import Utterance

    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    monkeypatch.setenv("VOICE_STANDALONE_MODULES", "environment")
    get_settings.cache_clear()

    transcript = [
        Utterance(
            role="user",
            content="me puede decir como va a estar el clima hoy",
        ),
        Utterance(
            role="agent",
            content="Señor, en Charlotte hoy nublado con 23 grados.",
        ),
    ]
    weather = resolve_standalone_forced_module(
        "me puede decir como va a estar el clima hoy",
        [],
        call_id="call-post-weather",
        user_id="user-1",
    )
    assert weather == "environment"

    for casual in ("ok gracias", "estas ahi", "¿Estás ahí?"):
        got = resolve_standalone_forced_module(
            casual,
            transcript,
            call_id="call-post-weather",
            user_id="user-1",
        )
        assert got is None, casual


def test_r6_voice_sequence_no_second_weather_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secuencia real r6: clima → ok gracias → sí me escuchas (sin 2.º clima)."""
    from app.services.retell_llm_types import Utterance

    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    monkeypatch.setenv("VOICE_STANDALONE_MODULES", "environment")
    get_settings.cache_clear()

    weather_q = "como traes clima el dia de hoy"
    weather_a = (
        "El clima actual en Charlotte presenta nublado con temperatura de 24 grados "
        "y humedad del 87 por ciento."
    )

    transcript_after_ack = [
        Utterance(role="user", content=weather_q),
        Utterance(role="agent", content=weather_a),
    ]
    transcript_after_checkin = transcript_after_ack + [
        Utterance(role="user", content="ok gracias"),
    ]

    assert (
        resolve_standalone_forced_module(
            weather_q,
            [],
            call_id="seq-r6",
            user_id="user-1",
        )
        == "environment"
    )
    assert (
        resolve_standalone_forced_module(
            "ok gracias",
            transcript_after_ack,
            call_id="seq-r6",
            user_id="user-1",
        )
        is None
    )
    assert (
        resolve_standalone_forced_module(
            "si me escuchas",
            transcript_after_checkin,
            call_id="seq-r6",
            user_id="user-1",
        )
        is None
    )


def test_location_followup_still_works_when_agent_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.retell_llm_types import Utterance

    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    monkeypatch.setenv("VOICE_STANDALONE_MODULES", "environment")
    get_settings.cache_clear()

    transcript = [
        Utterance(role="user", content="dame informacion de la calidad de aire"),
        Utterance(
            role="agent",
            content="¿Tiene alguna ubicación específica en mente, señor?",
        ),
    ]
    got = resolve_standalone_forced_module(
        "Charlotte",
        transcript,
        call_id="loc-ask",
        user_id="user-1",
    )
    assert got == "environment"
