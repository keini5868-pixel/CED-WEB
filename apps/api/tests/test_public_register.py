"""Registro manual público — validaciones (sin tocar Google OAuth)."""

from __future__ import annotations

import pytest

from app.services.public_register import PublicRegisterError, register_with_email


def test_register_requires_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.public_register.resend_configured",
        lambda: False,
    )
    with pytest.raises(PublicRegisterError) as exc:
        register_with_email(
            email="nuevo@example.com",
            password="segura123",
            full_name="Test",
        )
    assert exc.value.code == "resend_not_configured"


def test_register_rejects_weak_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.public_register.resend_configured",
        lambda: True,
    )
    with pytest.raises(PublicRegisterError) as exc:
        register_with_email(email="nuevo@example.com", password="short", full_name="Ana García")
    assert exc.value.code == "weak_password"


def test_register_rejects_short_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.public_register.resend_configured",
        lambda: True,
    )
    with pytest.raises(PublicRegisterError) as exc:
        register_with_email(email="nuevo@example.com", password="segura123", full_name="Al")
    assert exc.value.code == "invalid_name"
