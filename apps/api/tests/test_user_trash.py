"""Papelera: confirmación reforzada y scopes."""

from __future__ import annotations

from unittest.mock import patch

from app.services.user_trash import (
    detect_mass_delete_group,
    matches_pending_confirm,
    matches_strong_confirm,
    try_trash_turn,
)
from app.services import voice_client_session as vcs


def test_detect_finance_and_historial_scopes():
    assert detect_mass_delete_group("borra todo de finanzas") == "finance"
    assert detect_mass_delete_group("borrar todo en Finanzas") == "finance"
    assert detect_mass_delete_group("borra todo el historial de finanzas") == "finance"
    assert detect_mass_delete_group("borra todo el historial") == "historial"
    assert detect_mass_delete_group("borra todas las conversaciones") == "conversation"
    assert detect_mass_delete_group("elimina todas las imágenes") == "files"
    assert detect_mass_delete_group("hola") is None


def test_plain_yes_confirms_after_warning():
    assert matches_strong_confirm("sí", "finance") is False
    assert matches_pending_confirm("sí", "finance") is True
    assert matches_pending_confirm("dale", "finance") is True
    assert matches_pending_confirm("sí, borra todo el historial de finanzas", "finance")
    assert matches_strong_confirm("sí, borra todo el historial", "historial")
    assert not matches_strong_confirm(
        "sí, borra todo el historial", "finance"
    )


def test_trash_turn_asks_once_then_yes_is_enough():
    uid = "u-trash-1"
    vcs._sessions.pop(uid, None)
    first = try_trash_turn(uid, "borra todo de finanzas")
    assert first is not None
    assert first.get("needs_confirm") is True
    assert "sí" in first["spoken"].lower()
    assert "exactamente" not in first["spoken"].lower()

    with patch("app.services.user_trash.trash_group", return_value={"ok": True, "count": 3}):
        done = try_trash_turn(uid, "sí")
    assert done is not None
    assert done.get("deleted") == 3
    assert "papelera" in done["spoken"].lower()
    assert vcs.get_trash_pending(uid) is None


def test_repeat_delete_command_confirms():
    uid = "u-trash-repeat"
    vcs._sessions.pop(uid, None)
    try_trash_turn(uid, "borra todo de finanzas")
    with patch("app.services.user_trash.trash_group", return_value={"ok": True, "count": 2}):
        done = try_trash_turn(uid, "borra todo de finanzas")
    assert done is not None
    assert done.get("deleted") == 2


def test_cancel_aborts_pending_trash():
    uid = "u-trash-cancel"
    vcs._sessions.pop(uid, None)
    try_trash_turn(uid, "borra todo el historial")
    out = try_trash_turn(uid, "cancelar")
    assert out is not None
    assert "no borré" in out["spoken"].lower() or "cancelado" in out["spoken"].lower()
    assert vcs.get_trash_pending(uid) is None
