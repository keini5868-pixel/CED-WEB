"""Tests marketing creative intent and brief builder."""

from app.services.marketing_creative import (
    blocks_publish_intent,
    build_marketing_creative_brief,
    extract_product_subject,
    is_attachment_creative_request,
    is_image_creation_request,
    is_marketing_creative_intent,
    resolve_image_creation_from_attachment,
    should_build_creative_brief,
)
from app.services.publish_text import is_social_publish_intent


def test_informational_flyer_mention_is_not_creative_intent():
    msg = "análisis del flyer de la semana: el anuncio tiene poco contraste"
    assert is_marketing_creative_intent(msg) is False
    assert is_image_creation_request(msg) is False


def test_explain_flyer_is_not_creative_intent():
    msg = "necesito que me expliques el flyer de la semana"
    assert is_marketing_creative_intent(msg) is False
    assert is_image_creation_request(msg) is False


def test_marketing_creative_detects_flyer_request():
    msg = "genera una imagen donde tenga las especificaciones del basics y sus beneficios"
    assert is_marketing_creative_intent(msg)
    assert is_image_creation_request(msg)


def test_blocks_publish_for_creative_with_image():
    msg = "pon de fondo este producto y haz un flyer de venta con los beneficios"
    assert blocks_publish_intent(msg)
    assert not is_social_publish_intent(msg, with_image=True)


def test_strip_keeps_flyer_after_pon_de_fondo():
    from app.services.marketing_creative import strip_creative_user_noise

    msg = "pon de fondo este producto y haz un flyer de venta con los beneficios"
    cleaned = strip_creative_user_noise(msg)
    assert "flyer" in cleaned.lower()
    assert "beneficios" in cleaned.lower()
    assert cleaned != ""
    # Meta sola sí se vacía
    assert strip_creative_user_noise("usa esta imagen de referencia en el fondo") == ""
    assert strip_creative_user_noise("cambia el fondo a azul oscuro") == "cambia el fondo a azul oscuro"


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


def test_event_creative_brief_without_product_words():
    user_text = (
        "GENERA UNA IMAGEN CON ESTAS CARACTERISTICAS AI Summit 2026 es un evento tech en Charlotte. "
        "Puntos clave: Networking: Conecta con líderes del sector. "
        "Talleres: Sesiones prácticas de IA aplicada. "
        "Agenda: Charlas de 9am a 6pm. "
        "Y QUE ESPLIQUE ESTOS PUNTOS USANDO ESTA IMAGEN DE REFERENCIA EN EL FONDO"
    )
    internal, display, mode = build_marketing_creative_brief(
        user_text,
        history=None,
        has_reference_image=True,
    )
    assert mode == "edit"
    assert internal.startswith("[[CREATIVO]]")
    assert "GENERA UNA IMAGEN" not in internal.upper()
    assert "Tema:" in internal
    assert "Producto:" not in internal
    assert "Networking" in internal or "Talleres" in internal
    assert "AI Summit" in internal or "ai summit" in internal.lower()
    assert "Creativo" in display or "Flyer" in display


def test_attachment_creative_for_course_without_beneficios_word():
    text = (
        "Curso Python Pro es una formación online. "
        "Módulo 1: Fundamentos claros y prácticos. "
        "Módulo 2: Proyectos reales desde cero. "
        "Usa esta imagen de referencia en el fondo del flyer"
    )
    assert is_attachment_creative_request(text, None)
    assert should_build_creative_brief(text, has_reference_image=True)
    internal, _, _ = build_marketing_creative_brief(text, has_reference_image=True)
    assert "Módulo 1" in internal or "Fundamentos" in internal
    assert "referencia" not in internal.lower() or "PROHIBIDO" in internal


def test_extract_creative_subject_from_event_and_service():
    assert "charlotte" in extract_product_subject("Tour Charlotte es un recorrido guiado").lower()
    assert "python" in extract_product_subject("Curso Python Pro es una formación online").lower()
    assert "fitline" in extract_product_subject("producto basics de fitline con fibra").lower()


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
