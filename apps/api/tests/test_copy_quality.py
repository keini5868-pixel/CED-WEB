"""Tests copy quality — ortografía y textos literales para imágenes."""

from app.services.copy_quality import (
    build_flyer_headline,
    build_image_headline,
    compact_overlay_line,
    format_creative_image_copy,
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


def test_augment_image_prompt_plain_scene_has_no_instruction_words():
    from app.services.copy_quality import augment_image_prompt

    prompt = augment_image_prompt("Goku en Super Saiyan", "")
    low = prompt.lower()
    assert "goku" in low
    assert "instrucciones actuales" not in low
    assert "según este pedido" not in low
    assert "usuario" not in low
    assert "obligatorias" not in low
    assert "sin texto" in low


def test_build_image_headline_from_any_context():
    headline = build_image_headline(
        "Tour por Charlotte: historia y arquitectura moderna.",
        "Charlotte",
    )
    assert "charlotte" in headline.lower() or "Charlotte" in headline


def test_format_creative_image_copy_uses_short_titles_only():
    block = format_creative_image_copy(
        [
            "Salud intestinal: Contribuye a mantener flora equilibrada gracias a fibras",
            "Sistema inmune: Un intestino sano es clave para defensas fuertes",
        ],
        headline="FitLine Basics",
        max_lines=4,
    )
    assert "FitLine Basics" in block
    assert "Salud intestinal" in block
    assert "Contribuye a mantener" not in block
    assert "PROHIBIDO escribir" in block


def test_marketing_brief_universal_user_prompt_no_leakage():
    from app.services.marketing_creative import (
        build_marketing_creative_brief,
        strip_creative_user_noise,
    )

    user_text = (
        "GENERA UNA IMAGEN CON ESTAS CARACTERISTICAS FitLine Basics es un suplemento nutricional "
        "diseñado para apoyar la salud digestiva. Sus principales beneficios son: "
        "Salud intestinal: Contribuye a mantener una flora intestinal equilibrada. "
        "Mejor absorción: Ayuda a optimizar la absorción de nutrientes. "
        "Sistema inmune: Un intestino sano es clave para un sistema inmunológico fuerte. "
        "Y QUE ESPLIQUE SUS VBENEFICIOS USANDO ESTA IMEGENE DE REFERENCIA DEL PRODUCTO EN EL FONDO"
    )
    cleaned = strip_creative_user_noise(user_text)
    assert "referencia" not in cleaned.lower()
    assert "imegen" not in cleaned.lower()
    assert "FitLine Basics" in cleaned

    internal, display, mode = build_marketing_creative_brief(
        user_text,
        history=None,
        has_reference_image=True,
    )
    assert mode == "edit"
    assert internal.startswith("[[CREATIVO]]")
    assert "Instrucción del cliente" not in internal
    assert "GENERA UNA IMAGEN" not in internal.upper()
    assert "FitLine Basics" in internal or "fitline" in internal.lower()
    assert "Salud intestinal" in internal
    assert "Contribuye a mantener una flora" not in internal
    assert "Tema:" in internal
    assert "EN EL FONDO" not in display


def test_marketing_brief_real_estate_prompt_no_leakage():
    user_text = (
        "GENERA IMAGEN Vista Mar es un apartamento frente al mar. "
        "Puntos clave: Ubicación: Zona exclusiva y tranquila. "
        "Amenidades: Piscina, gym y seguridad 24h. "
        "Precio: Opciones de financiamiento flexibles. "
        "USA ESTA FOTO DE REFERENCIA EN EL FONDO"
    )
    internal, display, mode = build_marketing_creative_brief(
        user_text,
        history=None,
        has_reference_image=True,
    )
    assert mode == "edit"
    assert "GENERA IMAGEN" not in internal.upper()
    assert "Ubicación" in internal or "Amenidades" in internal
    assert "Vista Mar" in internal or "vista mar" in internal.lower()
    assert "EN EL FONDO" not in display


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
