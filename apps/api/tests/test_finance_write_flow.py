"""Tests — Finanzas escritura con confirmación (piloto nativo)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import voice_client_session as vcs
from app.services.finance_write_flow import (
    cancel_finance_write,
    confirm_finance_write,
    is_finance_write_cancel,
    is_finance_write_confirm,
    maybe_clear_finance_pending_on_topic_change,
    prepare_finance_write,
)

USER = "550e8400-e29b-41d4-a716-446655440099"
CALL = "call_finance_test_1"


def test_is_finance_write_confirm():
    assert is_finance_write_confirm("sí, regístralo")
    assert is_finance_write_confirm("dale, adelante")
    assert is_finance_write_confirm("Sí.", allow_short_yes=True)
    assert is_finance_write_confirm("sí", allow_short_yes=True)
    assert not is_finance_write_confirm("ok gracias")
    assert not is_finance_write_confirm("perfecto")


def test_is_finance_write_confirm_recognizes_accented_confirmalo():
    """Regresión (auditoría pre-lanzamiento): 'confírmalo' con tilde no era
    reconocido porque el regex solo cubría 'confirma'/'confirmado' sin acento,
    dejando la confirmación por voz sin efecto ('no detecté confirmación clara')."""
    assert is_finance_write_confirm("sí, confírmalo")
    assert is_finance_write_confirm("confírmalo")
    assert is_finance_write_confirm("confirmado")


def test_is_finance_write_cancel():
    assert is_finance_write_cancel("no, cancela")
    assert is_finance_write_cancel("mejor no")
    assert not is_finance_write_cancel("sí regístralo")


def test_prepare_transaction_creates_pending_draft():
    result = prepare_finance_write(
        USER,
        call_id=CALL,
        query="gasté 50 dólares en materiales hoy",
    )
    assert result["status"] == "awaiting_confirmation"
    assert result["ok"] is True
    assert result["transition"] == "transition_to_finance_confirm_pending"
    draft = vcs.get_finance_pending_write(USER)
    assert draft is not None
    assert draft["kind"] == "transaction"
    vcs.clear_finance_pending_write(USER)


def test_prepare_pending_payment_creates_draft():
    result = prepare_finance_write(
        USER,
        call_id=CALL,
        query="el lunes tengo que pagar 850",
    )
    assert result["status"] == "awaiting_confirmation"
    draft = vcs.get_finance_pending_write(USER)
    assert draft is not None
    assert draft["kind"] == "pending"
    vcs.clear_finance_pending_write(USER)


def test_prepare_requires_details():
    result = prepare_finance_write(USER, call_id=CALL, query="")
    assert result["status"] == "needs_query"

    result2 = prepare_finance_write(USER, call_id=CALL, query="cómo voy este mes")
    assert result2["status"] == "not_a_write"
    assert vcs.get_finance_pending_write(USER) is None


def test_confirm_requires_explicit_yes():
    prepare_finance_write(USER, call_id=CALL, query="gasté 50 en materiales")
    draft_id = vcs.get_finance_pending_write(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Desea que lo registre?"},
                {"role": "user", "content": "ok gracias"},
            ]
        }
    }
    result = confirm_finance_write(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["status"] == "confirm_required"
    assert vcs.get_finance_pending_write(USER)["status"] == "pending"
    vcs.clear_finance_pending_write(USER)


def test_confirm_short_yes_without_agent_context():
    """Un «sí» solo debe confirmar si hay borrador pendiente (sin exigir transcript del agente)."""
    prepare_finance_write(USER, call_id=CALL, query="el lunes tengo que pagar 850 en gasolina")
    draft_id = vcs.get_finance_pending_write(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "user", "content": "Sí."},
            ]
        }
    }
    with patch("app.services.finance_write_flow.save_transaction") as mock_save:
        mock_save.return_value = {
            "ok": True,
            "id": "tx-pending-1",
            "type": "gasto",
            "amount": "850",
            "currency": "USD",
            "category": "gasolina",
        }
        result = confirm_finance_write(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["ok"] is True
    assert result["status"] == "written"
    mock_save.assert_called_once()
    vcs.clear_finance_pending_write(USER)


def test_confirm_saves_transaction():
    prepare_finance_write(USER, call_id=CALL, query="gasté 50 en materiales hoy")
    draft_id = vcs.get_finance_pending_write(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Desea que lo registre?"},
                {"role": "user", "content": "sí, regístralo"},
            ]
        }
    }
    with patch("app.services.finance_write_flow.save_transaction") as mock_save:
        mock_save.return_value = {
            "ok": True,
            "id": "tx-1",
            "type": "gasto",
            "amount": "50",
            "currency": "USD",
        }
        result = confirm_finance_write(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["ok"] is True
    assert result["status"] == "written"
    assert result["transition"] == "transition_to_general_assistant"
    assert vcs.get_finance_pending_write(USER)["status"] == "written"
    mock_save.assert_called_once()
    vcs.clear_finance_pending_write(USER)


def test_confirm_idempotent_when_already_written():
    prepare_finance_write(USER, call_id=CALL, query="gasté 50 en materiales")
    draft_id = vcs.get_finance_pending_write(USER)["draft_id"]
    vcs.mark_finance_pending_written(USER, saved_ids=["tx-1"])
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Desea que lo registre?"},
                {"role": "user", "content": "sí, regístralo"},
            ]
        }
    }
    result = confirm_finance_write(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["status"] == "already_written"
    vcs.clear_finance_pending_write(USER)


def test_cancel_clears_draft():
    prepare_finance_write(USER, call_id=CALL, query="gasté 50 en materiales")
    draft_id = vcs.get_finance_pending_write(USER)["draft_id"]
    result = cancel_finance_write(USER, draft_id=draft_id)
    assert result["status"] == "cancelled"
    assert vcs.get_finance_pending_write(USER) is None


def test_topic_change_clears_pending():
    prepare_finance_write(USER, call_id=CALL, query="gasté 50 en materiales")
    maybe_clear_finance_pending_on_topic_change(USER, "get_environment")
    assert vcs.get_finance_pending_write(USER) is None


def test_prepare_replaces_old_draft():
    prepare_finance_write(USER, call_id=CALL, query="gasté 50 en materiales")
    old_id = vcs.get_finance_pending_write(USER)["draft_id"]
    prepare_finance_write(USER, call_id=CALL, query="gasté 80 en gasolina")
    new_id = vcs.get_finance_pending_write(USER)["draft_id"]
    assert new_id != old_id
    vcs.clear_finance_pending_write(USER)
