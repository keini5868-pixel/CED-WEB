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
    body, source = _extract_body_from_payload(payload)
    assert "Team meeting at 10:00" in body
    assert source == "html"


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
    body, source = _extract_body_from_payload(payload)
    assert body == "Plain body with real schedule details."
    assert source == "plain"


def test_extract_body_prefers_rich_html_over_trivial_plain():
    """Promocionales: plain trivial («ver en navegador») no debe ganarle al HTML real."""
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": _b64("View in browser")},
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": _b64(
                        "<h1>Mega Sale at Alibaba</h1>"
                        "<p>Get 40% off industrial equipment this week only. "
                        "Free shipping on orders over $500. Offer ends Sunday.</p>"
                    ),
                },
            },
        ],
    }
    body, source = _extract_body_from_payload(payload)
    assert source == "html"
    assert "40% off industrial equipment" in body


def test_extract_body_raw_fallback_when_full_parse_empty(monkeypatch):
    """format=full sin partes decodificables → fallback a format=raw con MIME real."""
    import email.message

    mime = email.message.EmailMessage()
    mime["From"] = "promo@alibaba.com"
    mime["Subject"] = "Deals"
    mime.set_content("View online")
    mime.add_alternative(
        "<p>Wholesale prices on electronics. Bulk discounts available now.</p>",
        subtype="html",
    )
    raw_b64 = base64.urlsafe_b64encode(bytes(mime)).decode().rstrip("=")

    class FakeResponse:
        def __init__(self, data: dict) -> None:
            self._data = data

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._data

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, url, **kwargs):
            params = kwargs.get("params") or {}
            if params.get("format") == "raw":
                return FakeResponse({"raw": raw_b64})
            # format=full: payload sin data decodificable (solo imagen)
            return FakeResponse(
                {
                    "snippet": "Deals",
                    "payload": {
                        "mimeType": "multipart/related",
                        "parts": [
                            {"mimeType": "image/png", "body": {"attachmentId": "x"}},
                        ],
                    },
                }
            )

    monkeypatch.setattr("app.services.google_gmail_api.httpx.Client", FakeClient)
    result = fetch_message_body_detail("token", "msg-raw")
    assert result.ok is True
    assert result.source == "html"
    assert "Wholesale prices on electronics" in result.text


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
    body, source = _extract_body_from_payload(payload)
    assert "Report due Friday 5pm" in body
    assert source == "html"


def test_extract_body_from_calendar_invite():
    ics = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "SUMMARY:Work Schedule for Monday\n"
        "DESCRIPTION:Shift A 7am-3pm. Shift B 3pm-11pm.\n"
        "DTSTART:20260713T070000\n"
        "END:VEVENT\n"
        "END:VCALENDAR"
    )
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/calendar", "body": {"data": _b64(ics)}},
        ],
    }
    body, source = _extract_body_from_payload(payload)
    assert source == "calendar"
    assert "Shift A 7am-3pm" in body


def test_extract_body_fetches_attachment_id(monkeypatch):
    html = "<p>Body stored as attachment in Gmail.</p>"

    class FakeClient:
        def get(self, url, **kwargs):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    if "/attachments/" in url:
                        return {"data": _b64(html)}
                    return {}

            return Resp()

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"attachmentId": "att-1", "size": 120},
            },
        ],
    }
    body, source = _extract_body_from_payload(
        payload,
        client=FakeClient(),  # type: ignore[arg-type]
        access_token="tok",
        message_id="msg-1",
    )
    assert source == "html"
    assert "Body stored as attachment" in body


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
