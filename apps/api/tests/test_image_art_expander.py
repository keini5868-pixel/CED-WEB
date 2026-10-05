"""Expander de escena — limpieza y contrato, sin llamar a Gemini."""

import pytest

from app.services.image_art_expander import (
    _clean_expander_output,
    _expander_changed_subject,
    expand_image_scene,
)


def test_clean_expander_strips_preamble_and_fences():
    raw = "```\nAquí tienes el prompt: A small cyan holographic robot on a metal base.\n```"
    cleaned = _clean_expander_output(raw)
    assert cleaned.lower().startswith("a small cyan")
    assert "aquí tienes" not in cleaned.lower()
    assert "```" not in cleaned


@pytest.mark.enable_image_expander
def test_expand_skips_without_api_key(monkeypatch):
    class _S:
        google_api_key = ""

    monkeypatch.setattr("app.config.get_settings", lambda: _S())
    scene, status = expand_image_scene("un águila volando", "", "none")
    assert scene is None
    assert status == "skip"


def test_expander_rejects_boat_when_anchor_is_creatine_tub():
    assert (
        _expander_changed_subject(
            "hombre con un bote de creatina en la mano",
            "A muscular man at a ship helm on a nautical deck.",
        )
        is True
    )
    assert (
        _expander_changed_subject(
            "hombre con un bote de creatina en la mano",
            "A muscular man holding a creatine tub under gym lighting.",
        )
        is False
    )
