"""Gate OpenAI Realtime — solo si VOICE_PROVIDER=openai (stack Cierre retirado)."""

from app.routers.openai import _allow_openai_realtime


def test_deny_realtime_for_cierre_when_retell_provider(monkeypatch):
    monkeypatch.setattr(
        "app.routers.openai.get_settings",
        lambda: type("S", (), {"voice_provider": "retell"})(),
    )
    assert not _allow_openai_realtime(
        "user-1",
        {"plan_id": "cierre", "voice_stack": "gemini", "voice_transport": "openai"},
    )


def test_deny_realtime_for_voice_transport_flag(monkeypatch):
    monkeypatch.setattr(
        "app.routers.openai.get_settings",
        lambda: type("S", (), {"voice_provider": "retell"})(),
    )
    assert not _allow_openai_realtime(
        "user-1",
        {"plan_id": "elite", "voice_transport": "openai"},
    )


def test_deny_realtime_for_elite_without_preview(monkeypatch):
    monkeypatch.setattr(
        "app.routers.openai.get_settings",
        lambda: type("S", (), {"voice_provider": "retell"})(),
    )
    assert not _allow_openai_realtime(
        "user-1",
        {"plan_id": "elite", "voice_stack": "retell", "voice_transport": "retell"},
        voice_profile="jarvis",
    )


def test_deny_realtime_admin_fitline_profile(monkeypatch):
    monkeypatch.setattr(
        "app.routers.openai.get_settings",
        lambda: type("S", (), {"voice_provider": "retell"})(),
    )
    assert not _allow_openai_realtime(
        "admin-1",
        {"plan_id": "elite", "voice_stack": "retell", "voice_transport": "retell"},
        voice_profile="fitline",
    )


def test_allow_when_global_openai_provider(monkeypatch):
    monkeypatch.setattr(
        "app.routers.openai.get_settings",
        lambda: type("S", (), {"voice_provider": "openai"})(),
    )
    assert _allow_openai_realtime(
        "user-1",
        {"plan_id": "elite", "voice_transport": "retell"},
    )


def test_normalize_plan_aliases():
    from app.domain.plans import normalize_plan_id

    assert normalize_plan_id("CED Cierre") == "cierre"
    assert normalize_plan_id("fitline") == "cierre"
    assert normalize_plan_id("pm-international") == "cierre"
