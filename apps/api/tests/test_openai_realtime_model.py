"""OPENAI_MODEL_VOICE must resolve to Realtime-capable IDs only."""

from app.services.openai_realtime import (
    DEFAULT_FITLINE_REALTIME_MODEL,
    DEFAULT_REALTIME_MODEL,
    _is_realtime_model,
    _models_to_try,
    _resolve_model,
)


def test_chat_model_rejected_for_realtime():
    assert not _is_realtime_model("gpt-4.1-mini-2025-04-14")
    assert not _is_realtime_model("gpt-4o")
    assert _is_realtime_model("gpt-realtime")
    assert _is_realtime_model("gpt-realtime-mini")
    assert _is_realtime_model("gpt-4o-mini-realtime-preview-2024-12-17")


def test_resolve_replaces_chat_model():
    assert _resolve_model("gpt-4.1-mini-2025-04-14") == DEFAULT_REALTIME_MODEL
    assert (
        _resolve_model("gpt-4.1-mini-2025-04-14", prefer_mini=True)
        == DEFAULT_FITLINE_REALTIME_MODEL
    )


def test_models_to_try_skips_chat_primary():
    models = _models_to_try("gpt-4.1-mini-2025-04-14")
    assert "gpt-4.1-mini-2025-04-14" not in models
    assert all(_is_realtime_model(m) for m in models)
    assert models[0] == DEFAULT_FITLINE_REALTIME_MODEL
