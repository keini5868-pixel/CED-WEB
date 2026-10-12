"""Centinela: parte, bitácora y aviso de corrección. Sin red ni Supabase."""

from __future__ import annotations

import pytest

from app.services import ced_sentinel
from app.services.ced_sentinel import (
    CORRECTING_HINT,
    begin_correction,
    end_correction,
    note_error,
    public_status,
    set_enabled,
    status_or_correction,
    sweep,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(ced_sentinel, "_save_state", lambda: None)
    monkeypatch.setattr(ced_sentinel, "_save_event", lambda event, quiet=False: None)
    monkeypatch.setattr(ced_sentinel, "_load_persisted", lambda: None)
    monkeypatch.setattr(ced_sentinel, "_start_thread", lambda: None)
    ced_sentinel.reset_for_tests()
    yield
    ced_sentinel.reset_for_tests()


def _check(level: str, title: str) -> dict:
    return {"level": level, "title": title, "detail": "detalle"}


def test_correction_hint_replaces_wait_copy():
    assert status_or_correction("user-1", "Generando imagen con IA…") == "Generando imagen con IA…"
    begin_correction("user-1", area="imagen", detail="reintento")
    assert status_or_correction("user-1", "Generando imagen con IA…") == CORRECTING_HINT
    begin_correction("user-1", area="imagen", detail="otro")
    end_correction("user-1")
    assert status_or_correction("user-1", "Generando documento…") == CORRECTING_HINT
    end_correction("user-1")
    assert status_or_correction("user-1", "Generando documento…") == "Generando documento…"


def test_correction_is_logged_only_while_guard_is_on():
    begin_correction("user-1", area="pdf", detail="retoma")
    assert public_status()["events"] == []
    end_correction("user-1")

    set_enabled(True)
    begin_correction("user-2", area="imagen", detail="Gemini no respondió")
    kinds = [event["kind"] for event in public_status()["events"]]
    assert kinds.count("correction") == 1
    end_correction("user-2")


def test_sweep_records_a_level_change_once(monkeypatch):
    monkeypatch.setattr(ced_sentinel, "_check_voice", lambda: _check("error", "Voz caída"))
    monkeypatch.setattr(ced_sentinel, "_check_payments", lambda: _check("ok", "Pagos operativos"))
    monkeypatch.setattr(ced_sentinel, "_check_data", lambda: _check("ok", "Datos operativos"))
    monkeypatch.setattr(ced_sentinel, "_check_models", lambda: _check("watch", "Modelos incompletos"))

    assert sweep() == []
    set_enabled(True)
    sweep()
    sweep()

    changes = [event for event in public_status()["events"] if event["kind"] == "change"]
    assert len(changes) == 4
    areas = {event["area"] for event in changes}
    assert areas == {"voz", "pagos", "datos", "modelos"}
    status = public_status()
    assert status["enabled"] is True
    assert len(status["checks"]) == 4


def test_note_error_dedupes_while_enabled():
    set_enabled(True)
    note_error("voz", "proveedor caído", "retell")
    note_error("voz", "proveedor caído", "retell")
    errors = [event for event in public_status()["events"] if event["kind"] == "error"]
    assert len(errors) == 1
    assert errors[0]["area"] == "voz"
