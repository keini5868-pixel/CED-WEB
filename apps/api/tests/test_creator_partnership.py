"""Modo Creador — overlay Jarvis solo para super admin."""

from app.domain.ced_identity import (
    CED_CREATOR_PARTNERSHIP,
    creator_partnership_overlay_for_user,
)
from app.services.retell_native_pilot import RETELL_NATIVE_PILOT_PROMPT


def test_creator_partnership_text_has_guardrails():
    assert "MODO CREADOR" in CED_CREATOR_PARTNERSHIP
    assert "Keini Castillo" in CED_CREATOR_PARTNERSHIP
    assert "YouTube" in CED_CREATOR_PARTNERSHIP
    assert "tareas serias" in CED_CREATOR_PARTNERSHIP
    assert "NO aplica" in CED_CREATOR_PARTNERSHIP


def test_creator_overlay_empty_without_user():
    assert creator_partnership_overlay_for_user(None) == ""
    assert creator_partnership_overlay_for_user("") == ""


def test_creator_overlay_only_for_super_admin(monkeypatch):
    import app.deps.auth as auth
    import app.services.supabase_db as supabase_db

    def fake_profile(user_id: str):
        if user_id == "admin-1":
            return {"email": "keini@castillodigital.com", "role": "super_admin"}
        return {"email": "cliente@example.com", "role": "user"}

    monkeypatch.setattr(supabase_db, "get_profile", fake_profile)
    monkeypatch.setattr(
        auth,
        "is_super_admin",
        lambda email, role=None: (email or "").lower() == "keini@castillodigital.com"
        or role == "super_admin",
    )

    assert "MODO CREADOR" in creator_partnership_overlay_for_user("admin-1")
    assert creator_partnership_overlay_for_user("user-2") == ""


def test_native_pilot_prompt_gates_creator_mode():
    assert "creator_mode={{creator_mode}}" in RETELL_NATIVE_PILOT_PROMPT
    assert "MODO CREADOR" in RETELL_NATIVE_PILOT_PROMPT
    assert "YouTube" in RETELL_NATIVE_PILOT_PROMPT
