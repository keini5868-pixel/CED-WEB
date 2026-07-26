"""Tests — router Gemini vs Ideogram en `generate_image()` y detector estricto de costo.

Diseño aprobado (Keini, 2026-07-20):
- Tier 4.0 Turbo ($0.03 real / $0.06 monedero) como default.
- Cuotas diarias: Starter 1, Pro 3, Élite 5, Founding 8, Básico gratis 0 (excluido
  por completo, sin fallback de monedero para este recurso específico).
- Router ESTRICTO: solo dispara con comillas explícitas o "que diga/ponga X" en el
  pedido ACTUAL — nunca por palabras genéricas de marketing ni por historial (ese es
  el riesgo de "disparar Ideogram de más" que Keini pidió evitar explícitamente).
- Cualquier falla de Ideogram degrada a Gemini sin exponer error al usuario.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.plans import PlanId, PlanLimits, get_plan_limits, unit_cost_usd
from app.services.copy_quality import prompt_requires_ideogram_text

# ---------------------------------------------------------------------------
# Cuotas por plan (aprobadas)
# ---------------------------------------------------------------------------


def test_ideogram_daily_quotas_match_approved_design():
    assert get_plan_limits(PlanId.STARTER.value).ai_images_text_per_day == 1
    assert get_plan_limits(PlanId.PRO.value).ai_images_text_per_day == 3
    assert get_plan_limits(PlanId.ELITE.value).ai_images_text_per_day == 5
    assert get_plan_limits(PlanId.FOUNDING.value).ai_images_text_per_day == 8


def test_free_basic_fully_excluded_from_ideogram_quota():
    assert get_plan_limits(PlanId.FREE_BASIC.value).ai_images_text_per_day == 0


def test_image_text_wallet_cost_is_006_with_003_real_margin():
    assert unit_cost_usd("image_text") == 0.06


def test_paid_plan_image_std_hd_caps_match_margin_calibrated_limits():
    assert get_plan_limits(PlanId.PRO.value).ai_images_standard_per_day == 18
    assert get_plan_limits(PlanId.PRO.value).ai_images_hd_per_day == 3


# ---------------------------------------------------------------------------
# Detector estricto — NO debe dispararse con palabras genéricas de marketing.
# ---------------------------------------------------------------------------


def test_strict_detector_true_for_explicit_quotes():
    assert prompt_requires_ideogram_text('Hazme un banner que diga "Gran Apertura"') is True


def test_strict_detector_true_for_que_diga_phrase():
    assert prompt_requires_ideogram_text("cartel que diga que hoy hay descuentos") is True


def test_strict_detector_true_for_que_ponga_phrase():
    assert prompt_requires_ideogram_text("un letrero que ponga Bienvenidos") is True


def test_strict_detector_true_for_con_el_texto_phrase():
    assert prompt_requires_ideogram_text("un letrero con el texto Bienvenidos") is True


def test_strict_detector_false_for_generic_marketing_words():
    # Estas palabras SÍ disparan `image_prompt_needs_verbatim_text` (amplio, para
    # decorar el prompt de Gemini) pero NO deben disparar el router de costo pagado.
    for text in (
        "hazme un flyer con los beneficios de mi taller de yoga",
        "genera una imagen publicitaria de mi evento",
        "necesito un anuncio para vender mi curso",
        "diseño con las características de mi producto",
        "banner: horarios y módulos del programa",
    ):
        assert prompt_requires_ideogram_text(text) is False, text


def test_strict_detector_false_for_plain_image_request():
    assert prompt_requires_ideogram_text("genera una imagen de un atardecer en la playa") is False


def test_strict_detector_false_for_empty_or_none():
    assert prompt_requires_ideogram_text("") is False
    assert prompt_requires_ideogram_text(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Router en generate_image()
# ---------------------------------------------------------------------------

IDEOGRAM_OK = {
    "ok": True,
    "raw_bytes": b"IDEOGRAM-BYTES",
    "mime_type": "image/png",
    "model": "ideogram-v4-turbo",
    "quality": "text",
    "provider": "ideogram",
    "estimated_cost_usd": 0.03,
}

GEMINI_OK = {
    "ok": True,
    "raw_bytes": b"GEMINI-BYTES",
    "mime_type": "image/png",
    "model": "gemini-2.5-flash-image",
    "quality": "standard",
    "provider": "gemini",
    "estimated_cost_usd": 0.01,
}


def _limits(*, text_cap: int, std_cap: int = 45, hd_cap: int = 5) -> PlanLimits:
    return PlanLimits(
        voice_minutes_per_day=18,
        web_searches_per_day=-1,
        ai_images_standard_per_day=std_cap,
        ai_images_hd_per_day=hd_cap,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=True,
        prospection_enabled=False,
        pdf_reports=True,
        claude_messages_per_day=-1,
        ai_images_text_per_day=text_cap,
    )


def _router_mocks(*, limits, day_counts=(0, 0, 0), ideogram_result=None, gemini_result=None):
    """Contexto de mocks compartido — deja pasar prepare_image_prompt real."""
    ideogram_result = ideogram_result if ideogram_result is not None else IDEOGRAM_OK
    gemini_result = gemini_result if gemini_result is not None else GEMINI_OK
    return (
        patch("app.services.gemini_images.supabase_db.get_profile", return_value={}),
        patch("app.services.gemini_images.is_super_admin", return_value=False),
        patch("app.services.gemini_images.effective_plan_limits", return_value=(limits, "ok", False)),
        patch("app.services.gemini_images._day_image_counts", return_value=day_counts),
        patch("app.services.ideogram_images.generate_image_ideogram", return_value=ideogram_result),
        patch("app.services.gemini_images.generate_image_gemini", return_value=gemini_result),
        patch("app.services.publish_media.store_publish_image_for_client", return_value="https://cdn.example.com/img.png"),
        patch("app.services.supabase_db.insert_generated_image"),
        patch(
            "app.services.gemini_images.get_settings",
            return_value=MagicMock(google_api_key="g-key", ideogram_api_key="ik-key"),
        ),
    )


def test_generate_image_uses_ideogram_when_preferred_and_within_free_quota():
    from app.services import gemini_images

    mocks = _router_mocks(limits=_limits(text_cap=5), day_counts=(0, 0, 0))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4] as mock_ideogram, mocks[5] as mock_gemini, mocks[6], mocks[7] as mock_insert, mocks[8]:
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt='banner que diga "Hola Mundo"',
            prefer_ideogram=True,
        )

    assert result["ok"] is True
    assert result["provider"] == "ideogram"
    mock_ideogram.assert_called_once()
    mock_gemini.assert_not_called()
    assert mock_insert.call_args.kwargs["quality"] == "text"


def test_generate_image_never_touches_ideogram_when_not_preferred():
    from app.services import gemini_images

    mocks = _router_mocks(limits=_limits(text_cap=5))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4] as mock_ideogram, mocks[5] as mock_gemini, mocks[6], mocks[7], mocks[8]:
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt="genera una imagen de un atardecer en la playa",
            prefer_ideogram=False,
        )

    assert result["ok"] is True
    assert result["provider"] == "gemini"
    mock_ideogram.assert_not_called()
    mock_gemini.assert_called_once()


def test_generate_image_excludes_ideogram_completely_for_free_basic():
    from app.services import gemini_images

    mocks = _router_mocks(limits=get_plan_limits(PlanId.FREE_BASIC.value))
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4] as mock_ideogram, mocks[5], mocks[6], mocks[7], mocks[8]:
        result = gemini_images.generate_image(
            user_id="user-basic",
            plan_id="free_basic",
            prompt='banner que diga "Hola"',
            prefer_ideogram=True,
        )

    assert result["ok"] is True
    assert result["provider"] == "gemini"
    assert result["ideogram_declined_reason"] == "basic_excluded"
    mock_ideogram.assert_not_called()


def test_generate_image_falls_back_to_gemini_when_ideogram_api_fails():
    from app.services import gemini_images

    mocks = _router_mocks(
        limits=_limits(text_cap=5),
        ideogram_result={"ok": False, "error": "timeout", "code": "ideogram_timeout"},
    )
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5] as mock_gemini, mocks[6], mocks[7], mocks[8]:
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt='banner que diga "Hola"',
            prefer_ideogram=True,
        )

    assert result["ok"] is True
    assert result["provider"] == "gemini"
    assert result["ideogram_declined_reason"] == "ideogram_failed"
    mock_gemini.assert_called_once()


def test_generate_image_skips_ideogram_when_quota_and_balance_both_exhausted():
    from app.services import gemini_images

    mocks = _router_mocks(limits=_limits(text_cap=5), day_counts=(0, 0, 5))
    with (
        mocks[0], mocks[1], mocks[2], mocks[3],
        mocks[4] as mock_ideogram,
        mocks[5],
        mocks[6], mocks[7], mocks[8],
        patch("app.services.wallet.can_afford", return_value=False),
    ):
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt='banner que diga "Hola"',
            prefer_ideogram=True,
        )

    assert result["provider"] == "gemini"
    assert result["ideogram_declined_reason"] == "no_quota_no_balance"
    mock_ideogram.assert_not_called()


def test_generate_image_charges_wallet_when_ideogram_used_beyond_daily_quota():
    from app.services import gemini_images

    spent: list[tuple[str, float]] = []
    mocks = _router_mocks(limits=_limits(text_cap=5), day_counts=(0, 0, 5))
    with (
        mocks[0], mocks[1], mocks[2], mocks[3],
        mocks[4] as mock_ideogram,
        mocks[5],
        mocks[6], mocks[7], mocks[8],
        patch("app.services.wallet.can_afford", return_value=True),
        patch(
            "app.services.wallet.try_spend",
            side_effect=lambda uid, resource, units=1.0: spent.append((resource, units))
            or {"ok": True, "balance_usd": 1.0},
        ),
    ):
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt='banner que diga "Hola"',
            prefer_ideogram=True,
        )

    assert result["provider"] == "ideogram"
    mock_ideogram.assert_called_once()
    assert spent == [("image_text", 1.0)]


def test_generate_image_no_wallet_charge_within_free_daily_quota():
    from app.services import gemini_images

    mocks = _router_mocks(limits=_limits(text_cap=5), day_counts=(0, 0, 0))
    with (
        mocks[0], mocks[1], mocks[2], mocks[3],
        mocks[4],
        mocks[5],
        mocks[6], mocks[7], mocks[8],
        patch("app.services.wallet.try_spend") as mock_spend,
    ):
        result = gemini_images.generate_image(
            user_id="user-pro",
            plan_id="pro",
            prompt='banner que diga "Hola"',
            prefer_ideogram=True,
        )

    assert result["provider"] == "ideogram"
    mock_spend.assert_not_called()
