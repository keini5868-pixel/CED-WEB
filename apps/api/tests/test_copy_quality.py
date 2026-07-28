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


def test_reference_prompt_never_uses_escena_pedida_label():
    from app.services.gemini_images import _prepare_reference_gemini_prompt, _reference_prompt
    from app.services.image_reference_generator import build_reference_prompt

    raw = (
        "la imagen que sea así tomando en cuenta que en la imagen deben ir "
        "los detalles escritos: GENERACIÓN DE IMÁGENES Y PDF, ANÁLISIS DE VISIÓN"
    )
    for mode in ("inspired", "variation", "edit"):
        brief = _reference_prompt(raw, mode)
        prepared = _prepare_reference_gemini_prompt(raw, mode)
        built = build_reference_prompt(raw, mode)
        for blob in (brief, prepared, built):
            # Etiqueta meta que se pintaba en píxeles — no como mención en anti-fuga.
            assert "escena pedida:" not in blob.lower(), blob
            assert "cambios pedidos:" not in blob.lower(), blob
            assert "la imagen que sea así" not in blob.lower(), blob
    assert "TEXTOS EXACTOS" in prepared or "tipografía" in prepared.lower()
    assert "generación de imágenes" in prepared.lower() or "visión" in prepared.lower()


def test_collect_overlay_skips_instructional_prose():
    from app.services.copy_quality import collect_image_overlay_lines

    assert collect_image_overlay_lines(
        "la imagen que sea así tomando en cuenta los detalles escritos",
        "",
    ) == []
    lines = collect_image_overlay_lines(
        "Incluye:\n- Generación de imágenes y PDF\n- Análisis de visión (cámara)",
        "",
    )
    assert any("generación" in ln.lower() or "imágenes" in ln.lower() for ln in lines)


def test_allcaps_image_request_does_not_become_textos_exactos():
    """Regresión modo avanzado: «ME GENERAS UNA IMAGEN…» se pintaba en la foto."""
    from app.services.copy_quality import (
        collect_image_overlay_lines,
        orchestrate_image_generation_brief,
    )

    adv = (
        "ME GENERAS UNA IMAGEN DE UN ALCON AGARRANDO VUELO "
        "A EL CIELO CON LLUVIAS FUERTES"
    )
    ctx = "HOLA Hola, señor. Modo avanzado listo"
    assert collect_image_overlay_lines(adv, ctx) == []
    orch = orchestrate_image_generation_brief(adv, context=ctx)
    assert orch["overlay_lines"] == []
    assert orch["wants_literal_text"] is False
    tech = orch["technical_prompt"].lower()
    assert "textos exactos" not in tech
    assert "sin texto" in tech
    assert "me generas" not in tech
    assert "hola" not in tech
    assert "alcon" in tech or "alcón" in tech


def test_history_capability_bullets_not_painted_on_new_scene():
    """Regresión chat: pedido nuevo de halcón no hereda viñetas CED del historial."""
    from app.services.copy_quality import orchestrate_image_generation_brief

    normal = (
        "OK AHORA GENERA UN ALCON ROBOTICO CON EL LOGO DE CED "
        "Y QUE ESTE COMO AGARRANDO VUELO"
    )
    hist = """## Núcleo Actual
- **Asistente de IA conversacional** — responde
- **Mentor en ventas y prospección** — estrategia
- **Consultor de marketing digital** — Meta
- **Inteligencia general** — charla
- **Memoria contextual** — recuerda
"""
    orch = orchestrate_image_generation_brief(normal, context=hist)
    assert orch["overlay_lines"] == []
    assert orch["wants_literal_text"] is False
    tech = orch["technical_prompt"].lower()
    assert "asistente de ia" not in tech
    assert "mentor en ventas" not in tech
    assert "textos exactos" not in tech
    assert "sin texto" in tech


def test_explicit_detalles_escritos_still_uses_context_bullets():
    from app.services.copy_quality import orchestrate_image_generation_brief

    msg = "generame una imagen con estos detalles escritos"
    hist = "- **Asistente de IA conversacional**\n- **Memoria contextual**"
    orch = orchestrate_image_generation_brief(msg, context=hist)
    assert orch["wants_literal_text"] is True
    assert any("asistente" in ln.lower() for ln in orch["overlay_lines"])


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
    assert "PROHIBIDO" in block
    assert "renderizar" in block.lower() or "escribir" in block.lower()


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
