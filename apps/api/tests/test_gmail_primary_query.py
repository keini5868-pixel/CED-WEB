"""Unit: Gmail category query uses q=category: not CATEGORY_PERSONAL label AND."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.google_gmail_api import list_messages_by_category


def test_primary_uses_category_query_not_personal_label():
    with patch("app.services.google_gmail_api.list_messages") as mock_list:
        mock_list.return_value = [
            {
                "id": "1",
                "from": "a@b.com",
                "from_name": "A",
                "subject": "Hi",
                "date": "",
                "relative_date": "",
                "snippet": "",
            }
        ]
        msgs = list_messages_by_category("tok", "primary", max_results=5)
    assert len(msgs) == 1
    assert mock_list.call_args.kwargs["query"] == "in:inbox category:primary"


def test_primary_falls_back_to_inbox_when_category_empty():
    with patch("app.services.google_gmail_api.list_messages", return_value=[]):
        with patch(
            "app.services.google_gmail_api.list_inbox_messages",
            return_value=[{"id": "inbox-1", "subject": "X"}],
        ) as mock_inbox:
            msgs = list_messages_by_category("tok", "primary", max_results=3)
    assert msgs[0]["id"] == "inbox-1"
    mock_inbox.assert_called_once()
