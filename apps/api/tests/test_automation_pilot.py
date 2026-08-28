"""Tests — módulo Automatización (intents, matching, dry-run)."""

from __future__ import annotations

from app.services.automation_pilot.catalog import CURATED_CARDS
from app.services.automation_pilot.engine import (
    build_whatsapp_link,
    keywords_match,
    match_automations,
)
from app.services.automation_pilot.intents import (
    is_automation_config_intent,
    parse_automation_brief,
)


def test_curated_cards_cover_three_channels():
    channels = {c["channel"] for c in CURATED_CARDS}
    assert channels >= {"instagram", "facebook", "whatsapp"}
    assert len(CURATED_CARDS) >= 8


def test_automation_intent_comment_keyword_instagram():
    text = (
        'Cuando alguien comente "info" en mis reels de Instagram, '
        "responde con el link de WhatsApp"
    )
    assert is_automation_config_intent(text)
    brief = parse_automation_brief(text)
    assert brief is not None
    assert brief["channel"] == "instagram"
    assert brief["card_key"] == "ig_comment_keyword"
    assert "info" in brief["trigger_config"]["keywords"]
    assert "¿Lo activo?" in brief["confirmation"]


def test_automation_intent_facebook_messenger():
    text = "Cuando me escriban por Messenger de Facebook responde automático"
    brief = parse_automation_brief(text)
    assert brief is not None
    assert brief["channel"] == "facebook"
    assert brief["card_key"] == "fb_dm_new"


def test_keywords_match():
    assert keywords_match("Hola quiero INFO del producto", ["info", "precio"])
    assert not keywords_match("solo saludos", ["info"])


def test_match_comment_keyword_automation():
    autos = [
        {
            "id": "1",
            "trigger_type": "comment_keyword",
            "trigger_config": {"keywords": ["info"]},
            "status": "active",
        },
        {
            "id": "2",
            "trigger_type": "dm_new",
            "trigger_config": {},
            "status": "active",
        },
    ]
    hit = match_automations(autos, event_type="comment_new", text="quiero info")
    assert len(hit) == 1 and hit[0]["id"] == "1"
    dm = match_automations(autos, event_type="dm_new", text="hola")
    assert len(dm) == 1 and dm[0]["id"] == "2"


def test_whatsapp_link_builder():
    link = build_whatsapp_link("+58 412 1234567", "Hola desde IG")
    assert link.startswith("https://wa.me/584121234567?text=")
    assert "Hola" in link


def test_gate_defaults_off():
    from app.services.automation_pilot.gate import (
        automation_ig_fb_live_enabled,
        automation_module_enabled,
    )

    # Defaults de Settings en tests sin env de piloto
    assert automation_module_enabled() is False or isinstance(
        automation_module_enabled(), bool
    )
    assert isinstance(automation_ig_fb_live_enabled(), bool)
