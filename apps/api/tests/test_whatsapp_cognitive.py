from app.services.whatsapp_cognitive import analyze_turn, classify_prospect_dna
from app.services.whatsapp_cloud import inbound_message_events


def test_dna_profiles():
    assert classify_prospect_dna("es urgente, lo necesito hoy") == "Urgente"
    assert classify_prospect_dna("explícame cómo funciona y la garantía") == "Analítico"
    assert classify_prospect_dna("eso parece una estafa, no creo") == "Escéptico"
    assert classify_prospect_dna("listo, cómo pago, lo quiero") == "Decidido"


def test_close_score_and_human_on_decided():
    row = analyze_turn("listo, cómo pago, lo quiero")
    assert row["prospect_dna"] == "Decidido"
    assert row["close_score"] >= 50
    assert "Misión cognitiva" in row["overlay"]


def test_payment_image_needs_human():
    row = analyze_turn("aquí va el comprobante de pago", has_image=True)
    assert row["human_alert"] in {"comprobante", "cierre"}


def test_inbound_image_event():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "999"},
                            "messages": [
                                {
                                    "from": "18001112222",
                                    "id": "wamid.img",
                                    "type": "image",
                                    "image": {
                                        "id": "media-1",
                                        "caption": "pagué",
                                        "mime_type": "image/jpeg",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    events = inbound_message_events(payload)
    assert len(events) == 1
    assert events[0]["kind"] == "image"
    assert events[0]["media_id"] == "media-1"
    assert events[0]["body"] == "pagué"
