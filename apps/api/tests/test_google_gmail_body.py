"""Tests — extracción de cuerpo Gmail (HTML multipart)."""

from __future__ import annotations

import base64

from app.services.google_gmail_api import (
    MessageBodyResult,
    _extract_body_from_payload,
    _html_to_plain,
    fetch_message_body_detail,
)


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_html_to_plain_strips_tags_and_keeps_schedule():
    html = (
        "<html><body><h1>Work Schedule</h1>"
        "<p>Monday shift starts at 8:00 AM in building B.</p>"
        "<p>Tuesday: inventory review at 2:30 PM.</p></body></html>"
    )
    plain = _html_to_plain(html)
    assert "Monday shift starts at 8:00 AM" in plain
    assert "inventory review at 2:30 PM" in plain
    assert "<p>" not in plain


def test_extract_body_from_html_only_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {
                    "data": _b64(
                        "<p>Team meeting at 10:00. Lunch break at noon.</p>"
                    ),
                },
            },
        ],
    }
    body = _extract_body_from_payload(payload)
    assert "Team meeting at 10:00" in body
    assert "Lunch break at noon" in body


def test_extract_body_prefers_plain_over_html():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": _b64("Plain body with real schedule details.")},
            },
            {
                "mimeType": "text/html",
                "body": {"data": _b64("<p>HTML should not win</p>")},
            },
        ],
    }
    body = _extract_body_from_payload(payload)
    assert body == "Plain body with real schedule details."


def test_extract_body_nested_multipart_related():
    inner_html = "<div>Report due Friday 5pm. Contact HR for questions.</div>"
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {"data": _b64(inner_html)},
                    },
                ],
            },
        ],
    }
    body = _extract_body_from_payload(payload)
    assert "Report due Friday 5pm" in body


def test_fetch_message_body_detail_html_source(monkeypatch):
  class FakeResponse:
      def raise_for_status(self) -> None:
          return None

      def json(self) -> dict:
          return {
              "snippet": "Work Schedule for Monday",
              "payload": {
                  "mimeType": "multipart/alternative",
                  "parts": [
                      {
                          "mimeType": "text/html",
                          "body": {
                              "data": _b64(
                                  "<p>Shift A: 7am-3pm. Shift B: 3pm-11pm.</p>"
                              ),
                          },
                      },
                  ],
              },
          }

  class FakeClient:
      def __init__(self, *args, **kwargs) -> None:
          pass

      def __enter__(self):
          return self

      def __exit__(self, *args) -> None:
          return None

      def get(self, *args, **kwargs):
          return FakeResponse()

  monkeypatch.setattr("app.services.google_gmail_api.httpx.Client", FakeClient)
  result = fetch_message_body_detail("token", "msg-123")
  assert isinstance(result, MessageBodyResult)
  assert result.ok is True
  assert result.source == "html"
  assert "Shift A: 7am-3pm" in result.text
