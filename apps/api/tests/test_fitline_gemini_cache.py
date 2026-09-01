"""Context Caching FitLine — unit tests (sin llamada real a Google)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.opportunities_pilot import fitline_gemini_cache as fgc


def test_fitline_knowledge_needed_keywords():
    assert fgc.fitline_knowledge_needed(None, "qué es FitLine") is True
    assert fgc.fitline_knowledge_needed(None, "hola") is False
    assert fgc.fitline_knowledge_needed(None, "qué es Excel") is False


def test_fitline_knowledge_needed_ignores_cierre_force(monkeypatch):
    monkeypatch.setattr(
        "app.services.opportunities_pilot.fitline_guide_mode.user_plan_is_fitline_focus",
        lambda _uid: True,
    )
    assert fgc.fitline_knowledge_needed("u-cierre", "qué es Excel") is False
    assert fgc.fitline_knowledge_needed("u-cierre", "qué es Restorate FitLine") is True


def test_build_fitline_context_cache_text_has_fitline_and_base():
    text = fgc.build_fitline_context_cache_text()
    assert len(text) >= fgc._MIN_CACHE_CHARS
    assert "FitLine" in text or "FITLINE" in text or "PM International" in text


def test_ensure_fitline_cached_content_creates_and_reuses(monkeypatch):
    fgc.reset_fitline_cache_state_for_tests()
    monkeypatch.setattr(fgc, "context_cache_enabled", lambda: True)

    created = MagicMock()
    created.name = "cachedContents/test-fitline-1"
    created.expire_time = None

    client = MagicMock()
    client.caches.create.return_value = created

    name1 = fgc.ensure_fitline_cached_content(client, "gemini-2.5-flash")
    assert name1 == "cachedContents/test-fitline-1"
    assert client.caches.create.call_count == 1

    name2 = fgc.ensure_fitline_cached_content(client, "gemini-2.5-flash")
    assert name2 == name1
    assert client.caches.create.call_count == 1  # reuse


def test_ensure_fitline_cached_content_disabled(monkeypatch):
    fgc.reset_fitline_cache_state_for_tests()
    monkeypatch.setattr(fgc, "context_cache_enabled", lambda: False)
    client = MagicMock()
    assert fgc.ensure_fitline_cached_content(client, "gemini-2.5-flash") is None
    client.caches.create.assert_not_called()


def test_ensure_fitline_cached_content_api_failure_returns_none(monkeypatch):
    fgc.reset_fitline_cache_state_for_tests()
    monkeypatch.setattr(fgc, "context_cache_enabled", lambda: True)
    client = MagicMock()
    client.caches.create.side_effect = RuntimeError("quota")
    assert fgc.ensure_fitline_cached_content(client, "gemini-2.5-flash") is None


def test_build_voice_system_omit_flags_shrink_prompt():
    from app.services.voice_llm_common import build_voice_system

    full = build_voice_system(None, "qué es FitLine Restorate")
    slim = build_voice_system(
        None,
        "qué es FitLine Restorate",
        omit_static_core=True,
        omit_fitline_knowledge=True,
    )
    assert len(slim) < len(full) * 0.5
    assert "HECHOS OBLIGATORIOS FITLINE" not in slim or len(slim) < 2000
