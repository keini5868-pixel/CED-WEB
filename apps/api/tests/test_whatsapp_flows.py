"""Tests — matching de flujos WhatsApp y parseo de webhook."""

from __future__ import annotations

from app.services.whatsapp_cloud import inbound_text_events
from app.services.whatsapp_flows import is_stop_message, match_flow


def test_keyword_flow_wins_over_catch_all():
    flows = [
        {
            "id": "1",
            "trigger_type": "catch_all",
            "keywords": "",
            "reply_text": "default",
            "enabled": True,
            "priority": 900,
        },
        {
            "id": "2",
            "trigger_type": "keyword",
            "keywords": "precio, costos",
            "reply_text": "El pack sale 47",
            "enabled": True,
            "priority": 10,
        },
    ]
    hit = match_flow(flows, "Hola, ¿cuál es el PRECIO?")
    assert hit is not None
    assert hit["id"] == "2"


def test_catch_all_when_no_keyword():
    flows = [
        {
            "id": "2",
            "trigger_type": "keyword",
            "keywords": "horario",
            "reply_text": "9 a 6",
            "enabled": True,
            "priority": 10,
        },
        {
            "id": "1",
            "trigger_type": "catch_all",
            "keywords": "",
            "reply_text": "default",
            "enabled": True,
            "priority": 900,
        },
    ]
    hit = match_flow(flows, "quiero info")
    assert hit is not None
    assert hit["id"] == "1"


def test_stop_detection():
    assert is_stop_message("STOP")
    assert is_stop_message("para")
    assert not is_stop_message("para mañana nos vemos")


def test_inbound_text_events_extract():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "12345"},
                            "messages": [
                                {
                                    "from": "18001230000",
                                    "id": "wamid.abc",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    events = inbound_text_events(payload)
    assert len(events) == 1
    assert events[0]["from"] == "18001230000"
    assert events[0]["body"] == "hola"
    assert events[0]["phone_number_id"] == "12345"
