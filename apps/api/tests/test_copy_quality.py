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


def test_lock_on_image_spelling_fixes_ia_and_prospeccion():
    from app.services.copy_quality import lock_on_image_spelling

    assert lock_on_image_spelling("Tu asistente de I4.") == "Tu asistente de IA."
    assert "Prospección" in lock_on_image_spelling(
        "Marketing Ventas. Prosaeccion."
    )
    assert (
        lock_on_image_spelling(
            "Tu asistente de IA. Marketing Ventas. Prosaeccion."
        )
        == "Tu asistente de IA. Marketing. Ventas. Prospección."
    )


def test_ced_tagline_fix_prompt_locks_ia_and_prospeccion():
    from app.services.copy_quality import build_direct_image_prompt

    brief = build_direct_image_prompt(
        "ok pero en la imagen anterior I4 y es IA, corrige Prosaeccion"
    )
    prompt = str(brief.get("prompt") or "")
    assert "I4" in prompt or "IA" in prompt
    assert "Prospección" in prompt
    assert "never" in prompt.lower() or "I4" in prompt
    assert brief.get("wants_literal_text") is True
    assert "Tu asistente de IA. Marketing. Ventas. Prospección." in prompt


def test_ced_logo_forces_literal_ced_wordmark_not_sec():
    from app.services.copy_quality import (
        build_direct_image_prompt,
        lock_on_image_spelling,
        prompt_requires_precise_text,
        user_requests_ced_wordmark,
    )

    raw = "generame una imagen del logo de CED"
    assert user_requests_ced_wordmark(raw) is True
    assert prompt_requires_precise_text(raw) is True
    brief = build_direct_image_prompt(raw)
    assert brief.get("wants_literal_text") is True
    prompt = str(brief.get("prompt") or "")
    low = prompt.lower()
    assert "ced" in low
    assert "c-e-d" in low or "letters c then e then d" in low
    assert "sec" in low  # aparece como grafía prohibida
    assert "never sec" in low or "never render sec" in low
    assert lock_on_image_spelling("SEC") == "CED"
    assert not user_requests_ced_wordmark("un robot futurista del sistema CED")


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
    assert "textos exactos" not in low
    assert "zero letters" in low or "sin texto" in low or "critical:" in low


def test_scene_prompt_never_becomes_textos_exactos_via_sin_texto():
    """Regresión: «Sin texto» activaba _IMAGE_TEXT_HINT por la palabra «texto»
    y usaba el brief como titular → Nano Banana pintaba el pedido en la foto."""
    from app.services.copy_quality import (
        augment_image_prompt,
        image_prompt_needs_verbatim_text,
        orchestrate_image_generation_brief,
    )
    from app.services.gemini_images import prepare_image_prompt

    samples = [
        "generame una imagen de un hombre recostado de un arbol en un atardecer",
        "un aguila volando sobre un cielo lluvioso",
        "un gato dormido en un sofa",
        "un atardecer en la playa",
        "un perro corriendo en el parque",
    ]
    for raw in samples:
        orch = orchestrate_image_generation_brief(raw)
        assert orch["wants_literal_text"] is False, raw
        assert orch["overlay_lines"] == [], raw
        tech = orch["technical_prompt"]
        assert "TEXTOS EXACTOS" not in tech, raw
        assert image_prompt_needs_verbatim_text(tech, "") is False, raw
        prepared = prepare_image_prompt(tech, "")
        low = prepared.lower()
        assert "textos exactos" not in low, prepared
        assert "ortografía española" not in low, prepared
        # No debe citar el pedido como línea a pintar.
        assert '- "' not in prepared and "- «" not in prepared, prepared
        aug = augment_image_prompt(tech, "")
        assert "TEXTOS EXACTOS" not in aug, aug


def test_explicit_que_diga_still_requests_verbatim():
    from app.services.copy_quality import (
        image_prompt_needs_verbatim_text,
        orchestrate_image_generation_brief,
    )

    msg = 'generame un banner que diga "Gran Apertura"'
    assert image_prompt_needs_verbatim_text(msg, "") is True
    orch = orchestrate_image_generation_brief(msg)
    assert orch["wants_literal_text"] is True
    tech = orch["technical_prompt"]
    assert "Gran Apertura" in tech or "apertura" in tech.lower()
    assert "include the requested labels" in tech.lower()
    assert "TEXTOS EXACTOS" in tech
    assert "FULL FRAME" in tech
    assert "SPELLING:" in tech
    assert "character-by-character" in tech.lower() or "carácter por carácter" in tech.lower()


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
    assert "no text, letters" in tech or "sin texto" in tech
    assert "me generas" not in orch["visual_brief"].lower()
    assert "hola" not in tech
    assert "alcon" in tech or "alcón" in tech
    assert "sistema ced" not in tech


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
    # Logo de CED pide letras C-E-D; no hereda las viñetas del historial.
    assert orch["wants_literal_text"] is True
    tech = orch["technical_prompt"].lower()
    assert "asistente de ia" not in tech
    assert "mentor en ventas" not in tech
    assert "c-e-d" in tech or "letters c then e then d" in tech
    assert "never render sec" in tech or "never sec" in tech
    assert "alcon" in tech or "alcón" in tech
    # El único copy forzado es el wordmark CED, no las viñetas del chat.
    assert '"ced"' in tech
    assert "inteligencia general" not in tech
    assert "memoria contextual" not in tech


def test_explicit_detalles_escritos_keeps_natural_language_not_history_bullets():
    """Path directo: no cosecha viñetas del historial; el NL del usuario basta."""
    from app.services.copy_quality import orchestrate_image_generation_brief

    msg = (
        "generame una imagen con estos detalles escritos: "
        "Asistente de IA conversacional y Memoria contextual"
    )
    hist = "- **Asistente de IA conversacional**\n- **Memoria contextual**"
    orch = orchestrate_image_generation_brief(msg, context=hist)
    assert orch["wants_literal_text"] is True
    tech = orch["technical_prompt"].lower()
    assert "asistente" in tech
    assert "memoria" in tech
    assert "sistema ced" not in tech
    assert "include the requested labels" in tech


def test_generic_prompts_never_inject_ced_branding():
    """Cualquier escena genérica debe ir directa, sin marca CED."""
    from app.services.copy_quality import orchestrate_image_generation_brief

    samples = [
        "generame una imagen de un águila volando sobre un cielo lluvioso",
        "un atardecer en la playa",
        "un gato dormido en un sofá",
        "genera un perro",
        "hazme una foto de una montaña nevada",
        "crea una imagen de un auto rojo clásico",
        "genera un atardecer",
    ]
    for prompt in samples:
        orch = orchestrate_image_generation_brief(prompt, context="")
        tech = orch["technical_prompt"].lower()
        assert "sistema ced" not in tech, prompt
        assert "infografía premium del sistema ced" not in tech, prompt
        assert "hud holog" not in tech, prompt
        assert "no text, letters" in tech or "sin texto" in tech
        assert len(orch["visual_brief"]) >= 3, prompt


def test_explicit_ced_request_keeps_brand_context():
    from app.services.copy_quality import orchestrate_image_generation_brief

    orch = orchestrate_image_generation_brief(
        "generame una imagen del sistema CED estilo futurista",
        context="",
    )
    tech = orch["technical_prompt"].lower()
    assert "ced" in tech
    assert "futurista" in tech or "cian" in tech or "hud" in tech


def test_detalles_escritos_with_ced_context_allows_brand():
    from app.services.copy_quality import orchestrate_image_generation_brief

    orch = orchestrate_image_generation_brief(
        "generame una imagen con estos detalles escritos del sistema CED",
        context="- **Asistente de IA conversacional**\n- **Memoria contextual**",
    )
    assert orch["wants_literal_text"] is True
    assert "ced" in orch["technical_prompt"].lower()


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


def test_scene_prompt_includes_safe_frame_not_spelling():
    from app.services.copy_quality import build_direct_image_prompt

    direct = build_direct_image_prompt("un águila volando sobre un cielo lluvioso")
    prompt = direct["prompt"]
    assert "FULL FRAME" in prompt
    assert "No text, letters" in prompt
    assert "SPELLING:" not in prompt
    assert "TEXTOS EXACTOS" not in prompt


def test_quoted_equipo_goes_verbatim_with_spelling_and_frame():
    from app.services.copy_quality import (
        build_direct_image_prompt,
        prompt_requires_precise_text,
    )

    msg = 'genera un flyer que diga "equipo"'
    assert prompt_requires_precise_text(msg) is True
    direct = build_direct_image_prompt(msg)
    assert direct["wants_literal_text"] is True
    prompt = direct["prompt"]
    assert "TEXTOS EXACTOS" in prompt
    assert "equipo" in prompt.lower()
    assert "FULL FRAME" in prompt
    assert "SPELLING:" in prompt
    assert "keep every vowel" in prompt.lower() or "u in equipo" in prompt.lower()


def test_graphic_formats_require_precise_text_unless_sin_texto():
    from app.services.copy_quality import prompt_requires_precise_text

    assert prompt_requires_precise_text("hazme un flyer de mi taller de yoga") is True
    assert prompt_requires_precise_text("banner con horarios del programa") is True
    assert prompt_requires_precise_text("un cartel para la tienda") is True
    assert prompt_requires_precise_text("flyer sin texto") is False
    assert prompt_requires_precise_text("genera una imagen publicitaria de mi evento") is False
    assert prompt_requires_precise_text("diseño con las características de mi producto") is False


def test_image_text_mode_literal_beats_decorative():
    from app.services.copy_quality import build_direct_image_prompt, resolve_image_text_mode

    flyer = 'Haz un flyer de FitLine con el texto "Energía pura"'
    assert resolve_image_text_mode(flyer) == "literal"
    direct = build_direct_image_prompt(flyer)
    assert direct["text_mode"] == "literal"
    low = direct["prompt"].lower()
    assert "energía pura" in low or "energia pura" in low
    assert "illegible technical interface" not in low

    carousel = (
        'Texto overlay: "Tu asistente de IA no es un chatbot genérico". '
        "Rostro holográfico de CED, estilo Jarvis, paleta cian."
    )
    assert resolve_image_text_mode(carousel) == "literal"
    mixed = build_direct_image_prompt(carousel)
    assert mixed["wants_literal_text"] is True
    assert "illegible technical interface" in mixed["prompt"]
    assert "chatbot genérico" in mixed["prompt"] or "chatbot generico" in mixed["prompt"].lower()


def test_image_text_mode_decorative_hologram_not_organic_false_positive():
    from app.services.copy_quality import build_direct_image_prompt, resolve_image_text_mode

    robot = "Ok genera esa imagen. Robot holográfico de CED flotando sobre una base."
    assert resolve_image_text_mode(robot) == "decorative"
    prompt = build_direct_image_prompt(robot)["prompt"]
    assert "No text, letters" not in prompt
    assert "illegible technical interface" in prompt
    assert "cyan" in prompt.lower() or "ced" in prompt.lower()

    eagle = "Un águila volando sobre las montañas"
    assert resolve_image_text_mode(eagle) == "none"
    assert "No text, letters" in build_direct_image_prompt(eagle)["prompt"]

    bath = "Un baño moderno con un espejo LED y una pantalla"
    assert resolve_image_text_mode(bath) == "none"

    discount = "generame una imagen del producto con el código de descuento en la mesa"
    assert resolve_image_text_mode(discount) == "none"
