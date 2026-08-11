"""Gate OpenAI Realtime para plan Cierre / preview admin."""

from app.routers.openai import _allow_openai_realtime


def test_allow_realtime_for_cierre_plan():
    assert _allow_openai_realtime(
        "user-1",
        {"plan_id": "cierre", "voice_stack": "gemini", "voice_transport": "openai"},
    )


def test_allow_realtime_for_voice_transport_flag():
    assert _allow_openai_realtime(
        "user-1",
        {"plan_id": "elite", "voice_transport": "openai"},
    )


def test_deny_realtime_for_elite_without_preview(monkeypatch):
    monkeypatch.setattr(
        "app.services.preview_persona.is_cierre_partner_preview",
        lambda _uid: False,
    )
    monkeypatch.setattr(
        "app.services.preview_persona.user_may_use_preview",
        lambda _uid: False,
    )
    assert not _allow_openai_realtime(
        "user-1",
        {"plan_id": "elite", "voice_stack": "retell", "voice_transport": "retell"},
        voice_profile="jarvis",
    )


def test_allow_realtime_admin_fitline_profile(monkeypatch):
    monkeypatch.setattr(
        "app.services.preview_persona.is_cierre_partner_preview",
        lambda _uid: False,
    )
    monkeypatch.setattr(
        "app.services.preview_persona.user_may_use_preview",
        lambda _uid: True,
    )
    assert _allow_openai_realtime(
        "admin-1",
        {"plan_id": "elite", "voice_stack": "retell", "voice_transport": "retell"},
        voice_profile="fitline",
    )


def test_normalize_plan_aliases():
    from app.domain.plans import normalize_plan_id

    assert normalize_plan_id("CED Cierre") == "cierre"
    assert normalize_plan_id("fitline") == "cierre"
    assert normalize_plan_id("pm-international") == "cierre"
