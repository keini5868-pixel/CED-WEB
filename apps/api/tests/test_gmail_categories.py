"""Tests — Gmail categories API."""

from __future__ import annotations

from unittest.mock import patch

from app.services.google_gmail_api import GMAIL_CATEGORY_LABELS, get_gmail_emails


def test_gmail_category_labels():
    assert GMAIL_CATEGORY_LABELS["primary"] == "CATEGORY_PERSONAL"
    assert GMAIL_CATEGORY_LABELS["promotions"] == "CATEGORY_PROMOTIONS"


def test_get_gmail_emails_by_category():
    sample = {
        "id": "1",
        "from": "JOMED LLC",
        "from_name": "JOMED LLC",
        "subject": "Work order",
        "date": "Hace 2 horas",
        "relative_date": "Hace 2 horas",
        "snippet": "Mañana",
    }
    with patch(
        "app.services.google_oauth.get_connection_status",
        return_value={"connected": True},
    ):
        with patch(
            "app.services.google_oauth.get_valid_access_token",
            return_value="token",
        ):
            with patch(
                "app.services.google_gmail_api.list_messages_by_category",
                return_value=[sample],
            ) as mock_list:
                result = get_gmail_emails("user-1", "promotions")

    assert result["connected"] is True
    assert result["category"] == "promotions"
    assert result["count"] == 1
    assert result["messages"][0]["from"] == "JOMED LLC"
    mock_list.assert_called_once()
    assert mock_list.call_args.args[1] == "promotions"
