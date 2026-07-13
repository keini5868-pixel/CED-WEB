"""Tests — vision_search truncation / spoken helpers."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

from app.services.vision_search import (
    VISION_ANALYZE_MAX_TOKENS,
    _spoken,
    analyze_image,
)


def test_spoken_cuts_on_sentence_boundary():
    text = (
        "Es una figura de resina color marrón. "
        "No veo marca legible. " + ("detalle " * 80)
    )
    out = _spoken(text, limit=120)
    assert out.endswith(".")
    assert "figura de resina" in out.lower()
    assert len(out) <= 120


def test_analyze_image_rejects_tiny_payload():
    tiny = base64.b64encode(b"tiny").decode()
    out = analyze_image(f"data:image/jpeg;base64,{tiny}")
    assert out["ok"] is False


def test_analyze_image_uses_raised_token_budget():
    with patch(
        "app.services.vision_search._gemini_vision",
        return_value="Es una figura de resina color marrón. No veo marca legible.",
    ) as mock_g:
        payload = base64.b64encode(b"x" * 1200).decode()
        out = analyze_image(f"data:image/jpeg;base64,{payload}", question="qué es esto")
    assert out["ok"] is True
    assert "figura de resina" in out["summary"].lower()
    assert mock_g.call_args.kwargs["max_tokens"] == VISION_ANALYZE_MAX_TOKENS


def test_gemini_vision_config_disables_thinking():
    """thinking_budget=0 evita el corte MAX_TOKENS que dejaba «Es una figura»."""
    from app.services import vision_search as vs

    captured: dict = {}

    class FakePart:
        @staticmethod
        def from_bytes(**kwargs):
            return kwargs

        @staticmethod
        def from_text(**kwargs):
            return kwargs

    class FakeTypes:
        Part = FakePart

        class Content:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class ThinkingConfig:
            def __init__(self, thinking_budget=None):
                self.thinking_budget = thinking_budget
                captured["thinking_budget"] = thinking_budget

        class GenerateContentConfig:
            def __init__(self, **kwargs):
                captured["config"] = kwargs
                self.kwargs = kwargs

    fake_response = MagicMock()
    fake_response.text = "Es una figura de resina."
    fake_response.candidates = [MagicMock(finish_reason="STOP")]
    fake_response.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=12,
        thoughts_token_count=None,
        total_token_count=22,
    )

    class FakeModels:
        def generate_content(self, **kwargs):
            captured["model"] = kwargs["model"]
            return fake_response

    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = FakeModels()

    fake_genai = MagicMock()
    fake_genai.Client = FakeClient
    fake_genai.types = FakeTypes

    with patch.object(
        vs,
        "get_settings",
        return_value=MagicMock(google_api_key="k", openai_api_key=""),
    ):
        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(genai=fake_genai),
                "google.genai": fake_genai,
            },
        ):
            text = vs._gemini_vision(b"jpeg-bytes-here", "describe", max_tokens=512)

    assert text == "Es una figura de resina."
    assert captured["thinking_budget"] == 0
    assert captured["config"]["max_output_tokens"] == 512
