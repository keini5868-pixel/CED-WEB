"""Tests marketing creative intent and brief builder."""

from app.services.marketing_creative import (
    blocks_publish_intent,
    build_marketing_creative_brief,
    extract_product_subject,
    is_attachment_creative_request,
    is_image_creation_request,
    is_marketing_creative_intent,
    resolve_image_creation_from_attachment,
)
from app.services.publish_text import is_social_publish_intent


def test_marketing_creative_detects_flyer_request():
    msg = "genera una imagen donde tenga las especificaciones del basics y sus beneficios"
    assert is_marketing_creative_intent(msg)
    assert is_image_creation_request(msg)


def test_blocks_publish_for_creative_with_image():
    msg = "pon de fondo este producto y haz un flyer de venta con los beneficios"
    assert blocks_publish_intent(msg)
    assert not is_social_publish_intent(msg, with_image=True)


def test_explicit_publish_still_works():
    msg = "publica esta imagen en facebook"
    assert is_social_publish_intent(msg, with_image=True)
    assert not blocks_publish_intent(msg)


def test_build_brief_extracts_subject_and_benefits():
    history = [
        {
            "role": "user",
            "content": "Dame beneficios del producto basics de fitline",
        },
        {
            "role": "model",
            "content": (
                "FitLine Basics es un suplemento nutricional.\n"
                "Salud intestinal: Contribuye a mantener flora equilibrada.\n"
                "Sistema inmune: Fortalece defensas naturales.\n"
                "Antioxidantes: Protege del estrés oxidativo."
            ),
        },
    ]
    internal, display, mode = build_marketing_creative_brief(
        "genera imagen con esa informacion y beneficios",
        history,
        has_reference_image=True,
    )
    assert mode == "edit"
    assert "Salud intestinal" in internal or "intestinal" in internal.lower()
    assert "basics" in display.lower() or "fitline" in display.lower()
    assert "Genera un creativo publicitario" not in display
    assert "Usa la foto adjunta" in internal


def test_attachment_resolver_for_product_photo():
    history = [
        {"role": "user", "content": "genera una imagen del basics con beneficios"},
    ]
    resolved = resolve_image_creation_from_attachment(
        "esta es la presentacion genera la imagen con sus caracteristicas como flyer",
        history,
    )
    assert resolved is not None
    assert resolved["style_mode"] == "edit"
    assert "Creativo" in resolved["display_label"] or "Flyer" in resolved["display_label"]


def test_extract_product_subject_generic():
    subject = extract_product_subject("producto basics de fitline con fibra y probioticos")
    assert "fitline" in subject.lower()


def test_attachment_detects_typo_benefits_and_reference_image():
    text = (
        "Salud intestinal: Contribuye a mantener flora equilibrada.\n"
        "Sistema inmune: Fortalece defensas naturales.\n"
        "Y QUE ESPLIQUE SUS VBENEFICIOS USANDO ESTA IMEGENE DE REFERENCIA DEL PRODUCTO EN EL FONDO"
    )
    history = [
        {
            "role": "model",
            "content": "FitLine Basics es un suplemento nutricional en polvo.",
        },
    ]
    assert is_attachment_creative_request(text, history)
    assert is_marketing_creative_intent(text)
    resolved = resolve_image_creation_from_attachment(text, history)
    assert resolved is not None
    assert resolved["style_mode"] == "edit"
    assert "TEXTOS EXACTOS" in resolved["internal_prompt"]
    assert "EN EL FONDO" not in resolved["display_label"]
