"""GPT Image como motor tipográfico preferido (Nano Banana default; Ideogram fallback)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.plans import PlanLimits, PROVIDER_COGS_IMAGE_TEXT_USD
from app.services.copy_quality import prompt_requires_precise_text
from app.services.gpt_images import GPT_IMAGE_MEDIUM_COST_USD


GPT_OK = {
    "ok": True,
    "raw_bytes": b"GPT-IMAGE-BYTES",
    "mime_type": "image/png",
    "model": "gpt-image-1.5",
    "quality": "text",
    "provider": "gpt_image",
    "estimated_cost_usd": GPT_IMAGE_MEDIUM_COST_USD,
}


def _limits(*, text_cap: int = 5) -> PlanLimits:
    return PlanLimits(
        voice_minutes_per_day=18,
        web_searches_per_day=-1,
        ai_images_standard_per_day=45,
        ai_images_hd_per_day=5,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=True,
        prospection_enabled=False,
        pdf_reports=True,
        claude_messages_per_day=-1,
        ai_images_text_per_day=text_cap,
    )


def test_precise_text_alias_matches_ideogram_detector():
    assert prompt_requires_precise_text('que diga "Hola"') is True
    assert prompt_requires_precise_text("hazme un flyer de yoga") is True
    assert prompt_requires_precise_text("atardecer en la playa") is False
    assert prompt_requires_precise_text("flyer sin texto") is False


def test_provider_cogs_covers_gpt_image_medium():
    assert PROVIDER_COGS_IMAGE_TEXT_USD >= GPT_IMAGE_MEDIUM_COST_USD


def test_generate_image_prefers_gpt_image_over_ideogram_when_openai_configured():
    from app.services import gemini_images

    with (
        patch("app.services.gemini_images.supabase_db.get_profile", return_value={}),
        patch("app.services.gemini_images.is_super_admin", return_value=False),
        patch(
            "app.services.gemini_images.effective_plan_limits",
            return_value=(_limits(), "ok", False),
        ),
        patch("app.services.gemini_images._day_image_counts", return_value=(0, 0, 0)),
        patch(
            "app.services.gpt_images.generate_image_gpt",
            return_value=GPT_OK,
        ) as mock_gpt,
        patch(
            "app.services.ideogram_images.generate_image_ideogram",
        ) as mock_ideogram,
        patch("app.services.gemini_images.generate_image_gemini") as mock_gemini,
        patch(
            "app.services.publish_media.store_publish_image_for_client",
            return_value="https://cdn.example.com/gpt.png",
        ),
        patch("app.services.supabase_db.insert_generated_image") as mock_insert,
        patch(
            "app.services.gemini_images.get_settings",
            return_value=MagicMock(
                google_api_key="g-key",
                ideogram_api_key="ik-key",
                openai_api_key="sk-test",
                openai_model_image="gpt-image-1.5",
            ),
        ),
    ):
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt='banner que diga "Gran Apertura"',
            prefer_ideogram=True,
        )

    assert result["ok"] is True
    assert result["provider"] == "gpt_image"
    assert result["ideogram_used"] is True
    assert result["literal_text_engine"] == "gpt_image"
    mock_gpt.assert_called_once()
    mock_ideogram.assert_not_called()
    mock_gemini.assert_not_called()
    assert mock_insert.call_args.kwargs["quality"] == "text"


def test_generate_image_falls_back_to_ideogram_when_gpt_fails():
    from app.services import gemini_images

    ideogram_ok = {
        "ok": True,
        "raw_bytes": b"IDEOGRAM-BYTES",
        "mime_type": "image/png",
        "model": "ideogram-v4-turbo",
        "quality": "text",
        "provider": "ideogram",
        "estimated_cost_usd": 0.03,
    }
    with (
        patch("app.services.gemini_images.supabase_db.get_profile", return_value={}),
        patch("app.services.gemini_images.is_super_admin", return_value=False),
        patch(
            "app.services.gemini_images.effective_plan_limits",
            return_value=(_limits(), "ok", False),
        ),
        patch("app.services.gemini_images._day_image_counts", return_value=(0, 0, 0)),
        patch(
            "app.services.gpt_images.generate_image_gpt",
            return_value={"ok": False, "error": "timeout", "code": "gpt_image_timeout"},
        ),
        patch(
            "app.services.ideogram_images.generate_image_ideogram",
            return_value=ideogram_ok,
        ) as mock_ideogram,
        patch("app.services.gemini_images.generate_image_gemini") as mock_gemini,
        patch(
            "app.services.publish_media.store_publish_image_for_client",
            return_value="https://cdn.example.com/ideo.png",
        ),
        patch("app.services.supabase_db.insert_generated_image"),
        patch(
            "app.services.gemini_images.get_settings",
            return_value=MagicMock(
                google_api_key="g-key",
                ideogram_api_key="ik-key",
                openai_api_key="sk-test",
                openai_model_image="gpt-image-1.5",
            ),
        ),
    ):
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt='letrero con el texto Bienvenidos',
            prefer_ideogram=True,
        )

    assert result["provider"] == "ideogram"
    mock_ideogram.assert_called_once()
    mock_gemini.assert_not_called()
