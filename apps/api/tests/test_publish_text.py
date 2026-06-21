"""Tests publish text extraction (P5)."""

from app.services.publish_text import extract_publish_body, strip_publish_instruction


def test_strip_publish_instruction():
    assert strip_publish_instruction("que diga hola mundo") == "hola mundo"
    assert strip_publish_instruction("El sistema ha llegado") == "El sistema ha llegado"


def test_extract_publish_body_facebook():
    body = extract_publish_body(
        "Hazme una publicación que diga el sistema CED ha llegado",
        platform="facebook",
    )
    assert body == "el sistema CED ha llegado"

    body2 = extract_publish_body("Publica en Facebook: hola mundo", platform="facebook")
    assert body2 == "hola mundo"


def test_extract_publish_body_instagram():
    body = extract_publish_body(
        "Publica en instagram que diga motivación diaria",
        platform="instagram",
    )
    assert body == "motivación diaria"
