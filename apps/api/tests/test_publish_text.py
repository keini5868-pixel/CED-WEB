"""Tests publish text extraction (P5)."""

from app.services.publish_text import (
    detect_publish_platform,
    extract_publish_body,
    is_social_publish_intent,
    strip_publish_instruction,
)


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


def test_is_social_publish_intent_typo_instagram():
    assert is_social_publish_intent("ced publica esta imagen en mi imtagram")
    assert is_social_publish_intent("publicame esta imagen en imtagram", with_image=True)
    assert is_social_publish_intent("publicame esta imagen en intagran", with_image=True)
    assert detect_publish_platform("publica en intagran") == "instagram"


def test_extract_user_caption():
    from app.services.publish_text import (
        extract_caption_from_turn,
        extract_user_caption_for_publish,
        is_publish_confirm,
        wants_publish_now,
    )

    assert extract_user_caption_for_publish(
        "el texto para la imagen es ceda llegado ya publicala con ese texto"
    ) == "ceda llegado ya"
    assert wants_publish_now("el texto para la imagen es ceda llegado ya publicala con ese texto")
    assert is_publish_confirm("si enviala", allow_short_yes=True)
    assert is_publish_confirm("sí envíala", allow_short_yes=True)
    assert extract_caption_from_turn("publicame esta imagen en intagran") == ""
