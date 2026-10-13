"""Centinela: parte, bitácora y aviso de corrección. Sin red ni Supabase."""

from __future__ import annotations

import pytest

from app.services import ced_sentinel
from app.services.ced_sentinel import (
    CORRECTING_HINT,
    anchored_brief,
    begin_correction,
    brief_drifts_from_request,
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
    monkeypatch.setattr(ced_sentinel, "_check_piloto", lambda: _check("ok", "Piloto OK"))
    monkeypatch.setattr(ced_sentinel, "_check_herramientas", lambda: _check("ok", "Tools OK"))
    monkeypatch.setattr(ced_sentinel, "_check_runtime_voz", lambda: _check("ok", "Runtime OK"))

    assert sweep() == []
    set_enabled(True)
    sweep()
    sweep()

    changes = [event for event in public_status()["events"] if event["kind"] == "change"]
    assert len(changes) == 7
    areas = {event["area"] for event in changes}
    assert areas == {
        "voz",
        "pagos",
        "datos",
        "modelos",
        "piloto",
        "herramientas",
        "runtime_voz",
    }
    status = public_status()
    assert status["enabled"] is True
    assert len(status["checks"]) == 7
    assert status.get("voice_stack")
    assert status.get("expectations")


def test_guard_corrects_only_while_it_stays_on():
    asked = 'un cartel que diga "Prospección IA" sobre fondo negro'
    produced = "Photorealistic poster on a black background"
    assert brief_drifts_from_request(produced, asked) is False

    set_enabled(True)
    assert brief_drifts_from_request(produced, asked) is True
    anchored = anchored_brief(produced, asked)
    assert "Prospección IA" in anchored
    assert brief_drifts_from_request(anchored, asked) is False

    same_topic = (
        "Un castillo rojo al amanecer sobre la colina, con luz cálida y cielo despejado."
    )
    other_topic = (
        "Un retrato de una bailarina en un estudio oscuro, con cortinas y focos."
    )
    assert brief_drifts_from_request(other_topic, same_topic) is True
    assert brief_drifts_from_request(same_topic, same_topic) is False


def test_note_error_dedupes_while_enabled():
    set_enabled(True)
    note_error("voz", "proveedor caído", "retell")
    note_error("voz", "proveedor caído", "retell")
    errors = [event for event in public_status()["events"] if event["kind"] == "error"]
    assert len(errors) == 1
    assert errors[0]["area"] == "voz"
