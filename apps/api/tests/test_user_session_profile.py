"""Tests — memoria persistente estructurada por cliente (ced_user_memory)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services.user_session_profile import (
    COOLING_DAYS,
    TIER_ADMIN,
    TIER_BASIC,
    TIER_FULL,
    TIER_MID,
    extract_updates_from_utterance,
    fields_for_tier,
    format_memory_prompt_block,
    touch_and_learn,
)


def test_basic_tier_only_name_and_niche():
    assert fields_for_tier(TIER_BASIC) == ("display_name", "business_niche")
    assert "last_topic" not in fields_for_tier(TIER_BASIC)
    assert "objections" in fields_for_tier(TIER_MID)
    assert "tech_decisions" in fields_for_tier(TIER_ADMIN)
    assert "tech_decisions" not in fields_for_tier(TIER_FULL)


def test_extract_name_and_niche_basic():
    patch_data = extract_updates_from_utterance(
        "Hola, me llamo Carla y tengo un negocio de nutrición deportiva",
        tier=TIER_BASIC,
    )
    assert patch_data.get("display_name") == "Carla"
    assert "nutrición" in (patch_data.get("business_niche") or "").lower()
    assert "last_topic" not in patch_data  # básico no guarda tema


def test_extract_mid_gets_topic_and_price_signal_fields():
    patch_data = extract_updates_from_utterance(
        "Me interesa el plan Pro, ¿cuánto cuesta la suscripción mensual?",
        tier=TIER_MID,
    )
    assert "pro" in (patch_data.get("plan_interest") or "").lower()
    assert patch_data.get("last_topic")


def test_extract_admin_tech_decision():
    patch_data = extract_updates_from_utterance(
        "Descartamos el robot genérico y ya resolvimos el logo en el pecho",
        tier=TIER_ADMIN,
        existing={},
    )
    assert patch_data.get("tech_decisions")
    assert any("descartamos" in d.lower() for d in patch_data["tech_decisions"])


def test_format_prompt_is_short_and_plan_gated():
    row = {
        "display_name": "Ana",
        "business_niche": "café",
        "plan_interest": "elite",
        "last_topic": "precios de voz",
        "objections": ["es caro"],
        "tech_decisions": ["no volver a proponer holograma genérico"],
        "last_conversation_at": "2026-08-20T12:00:00+00:00",
    }
    with (
        patch(
            "app.services.user_session_profile.resolve_memory_tier",
            return_value=TIER_BASIC,
        ),
        patch(
            "app.services.user_session_profile.get_user_memory",
            return_value=row,
        ),
    ):
        block = format_memory_prompt_block("user-1")
    assert "Ana" in block
    assert "café" in block
    assert "elite" not in block  # gated
    assert "historial" in block.lower() or "puntuales" in block.lower()
    assert "no holograma" not in block.lower()


def test_format_admin_includes_tech_decisions():
    row = {
        "display_name": "Keini",
        "tech_decisions": ["Ya resolvimos el ID PM fuera del registro"],
        "speaking_style_notes": "más directo",
    }
    with (
        patch(
            "app.services.user_session_profile.resolve_memory_tier",
            return_value=TIER_ADMIN,
        ),
        patch(
            "app.services.user_session_profile.get_user_memory",
            return_value=row,
        ),
    ):
        block = format_memory_prompt_block("admin-1")
    assert "ADMIN" in block
    assert "ID PM" in block
    assert "más directo" in block


def test_touch_and_learn_flags_hot_lead_on_repeated_price():
    existing = {"price_ask_count": 1, "topic_hits": {}, "objections": []}
    upserts: list[dict] = []
    insights: list[dict] = []

    def fake_upsert(_uid, patch):
        upserts.append(patch)
        return {**existing, **patch}

    def fake_capture(*_a, **kwargs):
        insights.append(kwargs)
        return {"ok": True}

    with (
        patch(
            "app.services.user_session_profile.resolve_memory_tier",
            return_value=TIER_MID,
        ),
        patch(
            "app.services.user_session_profile.get_user_memory",
            return_value=existing,
        ),
        patch("app.services.user_session_profile._upsert", side_effect=fake_upsert),
        patch(
            "app.services.insight_questions.capture_insight_question",
            side_effect=fake_capture,
        ),
    ):
        touch_and_learn("u1", "¿Cuánto cuesta el plan Pro otra vez?")

    assert upserts
    assert upserts[0].get("price_ask_count") == 2
    assert upserts[0].get("hot_lead_flagged_at")
    assert insights and insights[0].get("force") is True
    assert "hot_lead" in (insights[0].get("tags_extra") or [])


def test_touch_and_learn_flags_cooling_after_gap():
    last = (datetime.now(timezone.utc) - timedelta(days=COOLING_DAYS + 1)).isoformat()
    existing = {
        "last_conversation_at": last,
        "last_topic": "FitLine en México",
        "price_ask_count": 0,
        "topic_hits": {},
        "objections": [],
    }
    insights: list[dict] = []

    with (
        patch(
            "app.services.user_session_profile.resolve_memory_tier",
            return_value=TIER_MID,
        ),
        patch(
            "app.services.user_session_profile.get_user_memory",
            return_value=existing,
        ),
        patch(
            "app.services.user_session_profile._upsert",
            side_effect=lambda uid, patch: patch,
        ),
        patch(
            "app.services.insight_questions.capture_insight_question",
            side_effect=lambda *a, **k: insights.append(k) or {"ok": True},
        ),
    ):
        # Un saludo tras días sin hablar dispara cooling (antes de actualizar last_at)
        touch_and_learn("u2", "hola")

    assert any("cooling" in (i.get("tags_extra") or []) for i in insights)
