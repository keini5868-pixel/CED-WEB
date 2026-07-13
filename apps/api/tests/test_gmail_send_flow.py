"""Tests — Gmail envío con confirmación (piloto nativo)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services import voice_client_session as vcs
from app.services.gmail_send_flow import (
    cancel_gmail_send,
    confirm_gmail_send,
    is_gmail_send_cancel,
    is_gmail_send_confirm,
    maybe_clear_gmail_pending_on_topic_change,
    prepare_gmail_send,
)

USER = "550e8400-e29b-41d4-a716-446655440099"
CALL = "call_gmail_test_1"


def test_is_gmail_send_confirm():
    assert is_gmail_send_confirm("sí, envíalo")
    assert is_gmail_send_confirm("dale, adelante")
    assert is_gmail_send_confirm("sí", allow_short_yes=True)
    assert not is_gmail_send_confirm("ok gracias")
    assert not is_gmail_send_confirm("perfecto")


def test_is_gmail_send_cancel():
    assert is_gmail_send_cancel("no, cancela")
    assert is_gmail_send_cancel("mejor no")
    assert not is_gmail_send_cancel("sí envíalo")


def test_prepare_requires_subject():
    result = prepare_gmail_send(
        USER,
        call_id=CALL,
        to="jessica.25@gmail.com",
        subject="",
        body="Confirmo asistencia.",
    )
    assert result["status"] == "needs_subject"
    assert "asunto" in result["spoken"].lower()
    assert vcs.get_gmail_pending_send(USER) is None


def test_prepare_requires_recipient_and_body():
    r1 = prepare_gmail_send(USER, call_id=CALL, to="", subject="Hola", body="")
    assert r1["status"] == "needs_recipient"

    r2 = prepare_gmail_send(
        USER,
        call_id=CALL,
        to="bad-email",
        subject="Hola",
        body="Texto",
    )
    assert r2["status"] == "invalid_recipient"

    r3 = prepare_gmail_send(
        USER,
        call_id=CALL,
        to="a@b.com",
        subject="Hola",
        body="",
    )
    assert r3["status"] == "needs_body"


def test_prepare_creates_pending_draft():
    result = prepare_gmail_send(
        USER,
        call_id=CALL,
        to="jessica.25@gmail.com",
        subject="Reunión martes",
        body="Confirmo asistencia.",
    )
    assert result["ok"] is True
    assert result["status"] == "awaiting_confirmation"
    assert result["transition"] == "transition_to_gmail_confirm_pending"
    draft = vcs.get_gmail_pending_send(USER)
    assert draft is not None
    assert draft["status"] == "pending"
    assert draft["subject"] == "Reunión martes"
    vcs.clear_gmail_pending_send(USER)


def test_prepare_never_infers_subject_from_body():
    result = prepare_gmail_send(
        USER,
        call_id=CALL,
        to="jessica.25@gmail.com",
        subject="",
        body="Reunión del martes — confirmo asistencia.",
        query="envía correo a jessica.25@gmail.com dile que confirmo asistencia",
    )
    assert result["status"] == "needs_subject"
    vcs.clear_gmail_pending_send(USER)


def test_confirm_requires_explicit_yes():
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="jessica.25@gmail.com",
        subject="Test",
        body="Hola",
    )
    draft_id = vcs.get_gmail_pending_send(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Desea que lo envíe?"},
                {"role": "user", "content": "ok gracias"},
            ]
        }
    }
    result = confirm_gmail_send(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["status"] == "confirm_required"
    assert vcs.get_gmail_pending_send(USER)["status"] == "pending"
    vcs.clear_gmail_pending_send(USER)


def test_confirm_sends_with_short_yes():
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="jessica.25@gmail.com",
        subject="Test",
        body="Hola mundo",
    )
    draft_id = vcs.get_gmail_pending_send(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Desea que envíe el correo?"},
                {"role": "user", "content": "Sí."},
            ]
        }
    }
    with patch("app.services.gmail_send_flow.get_valid_access_token", return_value="tok"):
        with patch(
            "app.services.gmail_send_flow.send_message",
            return_value={"id": "msg-short"},
        ):
            result = confirm_gmail_send(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["ok"] is True
    assert result["status"] == "sent"
    vcs.clear_gmail_pending_send(USER)


def test_confirm_sends_with_explicit_yes():
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="jessica.25@gmail.com",
        subject="Test",
        body="Hola mundo",
    )
    draft_id = vcs.get_gmail_pending_send(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Confirma el envío del correo?"},
                {"role": "user", "content": "sí, envíalo"},
            ]
        }
    }
    with patch("app.services.gmail_send_flow.get_valid_access_token", return_value="tok"):
        with patch(
            "app.services.gmail_send_flow.send_message",
            return_value={"id": "msg-123"},
        ):
            result = confirm_gmail_send(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["ok"] is True
    assert result["status"] == "sent"
    assert vcs.get_gmail_pending_send(USER)["status"] == "sent"
    vcs.clear_gmail_pending_send(USER)


def test_confirm_idempotent_on_retry():
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="jessica.25@gmail.com",
        subject="Test",
        body="Hola",
    )
    draft_id = vcs.get_gmail_pending_send(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Desea confirmar el envío?"},
                {"role": "user", "content": "sí envíalo"},
            ]
        }
    }
    with patch("app.services.gmail_send_flow.get_valid_access_token", return_value="tok"):
        with patch(
            "app.services.gmail_send_flow.send_message",
            return_value={"id": "msg-456"},
        ) as send_mock:
            first = confirm_gmail_send(USER, call_id=CALL, payload=payload, draft_id=draft_id)
            second = confirm_gmail_send(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert first["status"] == "sent"
    assert second["status"] == "already_sent"
    assert send_mock.call_count == 1
    vcs.clear_gmail_pending_send(USER)


def test_cancel_clears_pending():
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="a@b.com",
        subject="X",
        body="Y",
    )
    draft_id = vcs.get_gmail_pending_send(USER)["draft_id"]
    result = cancel_gmail_send(USER, draft_id=draft_id)
    assert result["status"] == "cancelled"
    assert vcs.get_gmail_pending_send(USER) is None


def test_topic_change_clears_pending():
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="a@b.com",
        subject="X",
        body="Y",
    )
    maybe_clear_gmail_pending_on_topic_change(USER, "get_environment")
    assert vcs.get_gmail_pending_send(USER) is None


def test_new_prepare_invalidates_old_pending():
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="old@b.com",
        subject="Old",
        body="Old body",
    )
    old_id = vcs.get_gmail_pending_send(USER)["draft_id"]
    prepare_gmail_send(
        USER,
        call_id=CALL,
        to="new@b.com",
        subject="New",
        body="New body",
    )
    new_id = vcs.get_gmail_pending_send(USER)["draft_id"]
    assert old_id != new_id
    assert vcs.get_gmail_pending_send(USER)["to"] == "new@b.com"
    vcs.clear_gmail_pending_send(USER)
