"""Tests copy quality — ortografía y textos literales para imágenes."""

from app.services.copy_quality import (
    build_flyer_headline,
    build_image_headline,
    compact_overlay_line,
    format_verbatim_image_copy,
    normalize_spanish,
    overlay_lines_from_benefit_strings,
    polish_spanish_for_user,
)
from app.services.marketing_creative import build_marketing_creative_brief


def test_normalize_spanish_fixes_common_typos():
    assert "nutrición" in normalize_spanish("Nuturcion y digestión").lower()
    assert normalize_spanish("Sistema immune") == "Sistema inmune"
    assert "digestión" in normalize_spanish("Digestsión optima").lower()


def test_compact_overlay_line_short_and_clean():
    line = compact_overlay_line(
        "Salud intestinal",
        "Contribuye a mantener una flora intestinal equilibrada gracias a fibras.",
    )
    assert line.startswith("Salud intestinal")
    assert "equilibr" in line.lower() or line == "Salud intestinal"


def test_format_verbatim_image_copy_requires_literal_text():
    block = format_verbatim_image_copy(
        ["Salud intestinal: flora equilibrada", "Sistema inmune: defensas naturales"],
        headline="Bienestar diario",
    )
    assert "CARÁCTER POR CARÁCTER" in block
    assert "Bienestar diario" in block
    assert "equilibrada" in block


def test_augment_image_prompt_generic_castle():
    from app.services.copy_quality import augment_image_prompt

    prompt = augment_image_prompt(
        "Genera un póster de un castillo medieval con el título «La Fortaleza»",
        "Evento La Fortaleza: aventura épica para toda la familia.",
    )
    assert "Ortografía española" in prompt
    assert "TEXTOS EXACTOS" in prompt or "Fortaleza" in prompt


def test_build_image_headline_from_any_context():
    headline = build_image_headline(
        "Tour por Charlotte: historia y arquitectura moderna.",
        "Charlotte",
    )
    assert "charlotte" in headline.lower() or "Charlotte" in headline


def test_marketing_brief_includes_verbatim_block():
    history = [
        {
            "role": "model",
            "content": (
                "FitLine Basics es un suplemento.\n"
                "Salud intestinal: Contribuye a mantener flora equilibrada.\n"
                "Sistema inmune: Fortalece las defensas naturales.\n"
                "Antioxidantes: Protege del estrés oxidativo."
            ),
        },
    ]
    internal, display, mode = build_marketing_creative_brief(
        "genera flyer con beneficios",
        history,
        has_reference_image=True,
    )
    assert "TEXTOS EXACTOS" in internal
    assert "ortografía" in internal.lower()
    assert "Salud intestinal" in internal
    assert "TEXTOS EXACTOS" in internal
    assert "Nutrición y digestión óptima" not in internal or "intestinal" in internal
    assert "Creativo" in display or "Flyer" in display


def test_polish_spanish_for_user():
    text = polish_spanish_for_user("Sistema immune y nutricion diaria")
    assert "inmune" in text
    assert "nutrición" in text
