"""Routing publicación vs creativo — casos reales del chat."""

from app.services.chat_intents import parse_followup_image_prompt
from app.services.marketing_creative import blocks_publish_intent, extract_product_subject
from app.services.publish_text import (
    detect_publish_platform_explicit,
    is_publish_platform_reply,
    is_social_publish_intent,
)


def test_publish_with_caracteristicas_not_blocked():
    msg = (
        "publica esta imagen en facebook con estas caracteristicas "
        "intestinal Antioxidantes"
    )
    assert is_social_publish_intent(msg, with_image=True)
    assert not blocks_publish_intent(msg)


def test_perfecto_publica_esto_en_facebook():
    msg = "perfecto publica esto en facebook"
    assert is_social_publish_intent(msg)
    assert not blocks_publish_intent(msg)


def test_en_face_is_platform_reply_not_image_prompt():
    assert is_publish_platform_reply("en face")
    assert detect_publish_platform_explicit("en face") == "facebook"
    history = [
        {"role": "user", "content": "genera creativo fitline"},
        {"role": "model", "content": "Creativo — FitLine Basics"},
    ]
    assert parse_followup_image_prompt("en face", history) is None


def test_subject_not_con_estas_caracteristicas():
    blob = (
        "GENERA UNA IMAGEN CON ESTAS CARACTERISTICAS FitLine Basics es un suplemento "
        "nutricional diseñado para apoyar la salud digestiva."
    )
    subject = extract_product_subject(blob)
    assert "fitline" in subject.lower()
    assert "caracter" not in subject.lower()


def test_generate_image_with_instagram_in_list_is_not_publish():
    msg = (
        "generame una imagen con estos detalles resumidos escritos\n"
        "- Asistente de IA conversacional\n"
        "- publicar_facebook / publicar_instagram — publica contenido\n"
        "- Memoria contextual\n"
    )
    assert not is_social_publish_intent(msg)
    assert blocks_publish_intent(msg)


def test_orchestrate_summarizes_long_markdown_to_short_labels():
    from app.services.copy_quality import orchestrate_image_generation_brief

    msg = (
        "generame una imagen con estos detalles resumidos escritos\n"
        "## Núcleo\n"
        "- **Asistente de IA conversacional** — responde en español\n"
        "- **Mentor en ventas** — estrategia comercial\n"
        "- **Consultor de marketing digital** — Meta Ads\n"
    )
    brief = orchestrate_image_generation_brief(msg)
    assert brief["wants_literal_text"] is True
    assert len(brief["overlay_lines"]) >= 2
    assert all(len(x) <= 40 for x in brief["overlay_lines"])
    assert "generame" not in brief["technical_prompt"].lower()
    assert "TEXTOS EXACTOS" in brief["technical_prompt"]
