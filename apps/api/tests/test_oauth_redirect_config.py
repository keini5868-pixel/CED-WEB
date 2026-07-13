"""Tests — redirect URIs OAuth Google apuntan al dominio API."""

from __future__ import annotations

from app.config import Settings


def test_oauth_redirect_rewrites_web_domain_to_api():
    settings = Settings(
        api_public_url="https://ced-web-production.up.railway.app",
        web_public_url="https://cedweb-production.up.railway.app",
        google_calendar_redirect_uri=(
            "https://cedweb-production.up.railway.app/auth/google/calendar/callback"
        ),
        google_gmail_redirect_uri=(
            "https://cedweb-production.up.railway.app/auth/google/gmail/callback"
        ),
    )
    assert (
        settings.google_calendar_redirect_uri
        == "https://ced-web-production.up.railway.app/auth/google/calendar/callback"
    )
    assert (
        settings.google_gmail_redirect_uri
        == "https://ced-web-production.up.railway.app/auth/google/gmail/callback"
    )


def test_oauth_redirect_keeps_api_domain_when_already_correct():
    settings = Settings(
        api_public_url="https://ced-web-production.up.railway.app",
        google_calendar_redirect_uri=(
            "https://ced-web-production.up.railway.app/auth/google/calendar/callback"
        ),
    )
    assert (
        settings.google_calendar_redirect_uri
        == "https://ced-web-production.up.railway.app/auth/google/calendar/callback"
    )
