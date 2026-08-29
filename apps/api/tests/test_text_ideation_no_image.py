"""Ideación de texto (idea/concepto/copy) NO debe disparar generación de imagen."""

from __future__ import annotations

from app.services.chat_image_generation import should_take_direct_image_path
from app.services.chat_intents import (
    is_generate_image_intent,
    is_text_ideation_request,
)
from app.services.marketing_creative import (
    is_image_creation_request,
    is_marketing_creative_intent,
)


_IDEA_ONLY = [
    "dame una idea de copy para Instagram",
    "dame una idea para un post",
    "necesito una idea de contenido",
    "quiero un concepto para un video",
    "dame ideas de copy",
    "sugiéreme un concepto creativo",
    "escribe un copy para mi producto",
    "dame una descripción de producto",
    "genera una idea de campaña",
    "hazme una idea de creativo",
    "dame una idea de creativo para instagram",
    "dame una idea de imagen para el feed",
    "quiero ideas para un flyer",
    "proponme un concepto de banner",
    "ayúdame con el copy del creativo",
    "dame el concepto de la imagen",
    "qué idea de imagen me recomiendas",
    "crea un concepto visual",
    "hazme un prompt para vender Activise",
    "dame una idea de contenido sobre Restorate",
    "necesito un prompt para Midjourney de FitLine",
    "escribe un prompt para ChatGPT sobre el producto",
]


_EXPLICIT_IMAGE = [
    "genera una imagen de un atardecer",
    "hazme una foto de un gato",
    "créame una imagen del producto",
    "Diseña un creativo para Meta Ads",
    "generame un flyer con los beneficios",
    "quiero un flyer de Restorate",
    "dame una imagen de un gato",
]


def test_idea_requests_are_text_ideation():
    for msg in _IDEA_ONLY:
        assert is_text_ideation_request(msg) is True, msg


def test_idea_requests_do_not_trigger_image_intent():
    for msg in _IDEA_ONLY:
        assert is_generate_image_intent(msg) is False, msg
        assert should_take_direct_image_path(msg, []) is False, msg
        assert is_image_creation_request(msg, []) is False, msg
        assert is_marketing_creative_intent(msg) is False, msg


def test_informational_copy_does_not_trigger_image():
    msgs = [
        "te paso la información del producto Restorate y sus beneficios",
        "aquí está el texto para el post de Instagram",
        "el diseño de la campaña se basa en tres pilares",
        "la imagen de marca debe transmitir confianza",
        "estos son los puntos del flyer de la semana pasada",
        "análisis del anuncio de Facebook: CTR bajo y copy largo",
        "Listo, señor, el creativo de Meta Ads necesita mejor titular",
        "dame la información del diseño de la campaña",
        "necesito que me expliques el flyer de la semana",
        "quiero el análisis del banner, no una imagen nueva",
    ]
    for msg in msgs:
        assert is_generate_image_intent(msg) is False, msg
        assert should_take_direct_image_path(msg, []) is False, msg
        assert is_image_creation_request(msg, []) is False, msg
        assert is_marketing_creative_intent(msg) is False, msg


def test_explicit_image_requests_still_work():
    for msg in _EXPLICIT_IMAGE:
        assert is_text_ideation_request(msg) is False, msg
        assert is_generate_image_intent(msg) is True, msg
        assert should_take_direct_image_path(msg, []) is True, msg


def test_talking_about_an_attached_image_does_not_generate():
    msgs = [
        "No se adjuntó la imagen. Intenta de nuevo en unos segundos.",
        "en esta imagen se nota que hay un detalle de 5 minutos por día",
        "ced le di estas instrucciones en esta imagen",
        "me generó una imagen y no era la intención",
        "la imagen adjunta muestra la tabla de usuarios",
    ]
    for msg in msgs:
        assert is_generate_image_intent(msg) is False, msg
        assert should_take_direct_image_path(msg, []) is False, msg
        assert is_image_creation_request(msg, []) is False, msg


def test_generate_image_with_idea_in_scene_still_images():
    """«genera una imagen de una idea abstracta» sigue siendo pedido visual."""
    msg = "genera una imagen de una idea abstracta flotando en el cielo"
    assert is_text_ideation_request(msg) is False
    assert is_generate_image_intent(msg) is True


def test_image_choice_confirmation_does_not_look_like_new_image_intent():
    from app.services.chat_image_generation import should_take_direct_image_path
    from app.services.chat_intents import is_image_choice_confirmation

    msg = "Ok. Te sigo. Que sea la primera."
    assert is_generate_image_intent(msg) is False
    assert is_image_choice_confirmation(msg) is True
    assert should_take_direct_image_path(msg, []) is False
    assert is_image_choice_confirmation(
        "¿Cuál es la pregunta que tú le haces después de las 3 preguntas de interés?"
    ) is False


def test_image_choice_confirmation_generates_after_phrase_options():
    from app.services.chat_image_generation import (
        resolve_voice_image_prompt,
        should_generate_image_from_voice_turn,
        should_take_direct_image_path,
    )
    from app.services.chat_intents import resolve_confirmed_image_prompt

    history = [
        {
            "role": "user",
            "content": (
                "El meta de una imagen que tenga el logo oficial de PM y el logo "
                "oficial de CED uniéndose. Abajo una frase impactante. "
                "Antes de crear la imagen, dime qué frase sería buena."
            ),
        },
        {
            "role": "assistant",
            "content": (
                '1. "CED & PM: La inteligencia que convierte la complejidad '
                'del multinivel en resultados automáticos." (Enfocada en eficiencia). '
                '2. "Donde la tecnología del Castillo se une al poder de FitLine." '
                '3. "Deja de descifrar el negocio y empieza a escalarlo."'
            ),
        },
    ]
    msg = "Ok. Te sigo. Que sea la primera."
    assert should_take_direct_image_path(msg, history) is True
    assert should_generate_image_from_voice_turn(msg, "", history) is True
    rebuilt = resolve_confirmed_image_prompt(msg, history)
    assert rebuilt is not None
    assert "CED & PM: La inteligencia" in rebuilt
    assert "logo oficial" in rebuilt.lower()
    llm = (
        "Imagen de los wordmarks CED y PM International uniéndose, con la frase "
        "CED & PM: La inteligencia que convierte la complejidad del multinivel "
        "en resultados automáticos."
    )
    assert should_generate_image_from_voice_turn(msg, llm, []) is True
    assert "inteligencia" in resolve_voice_image_prompt(msg, llm, []).lower()


def test_need_photo_for_instagram_without_generate_is_not_image_intent():
    msgs = [
        "I need a photo for Sek's Instagram, but I need before creating it that we agree to do something shocking",
        "Necesito una foto para el Instagram de Sek, pero antes de crearla tenemos que acordar hacer algo impactante",
        "Necesito una imagen para el Instagram de Sek",
        "I need a photo for Sek's Instagram",
        "Necesito una imagen para mi perfil",
    ]
    for msg in msgs:
        assert is_text_ideation_request(msg) is True, msg
        assert is_generate_image_intent(msg) is False, msg
        assert should_take_direct_image_path(msg, []) is False, msg
        assert is_image_creation_request(msg, []) is False, msg


def test_explicit_generate_after_brief_still_creates_image():
    msg = "Ok, genera la imagen: Sek en un traje negro rompiendo un cartel de Instagram"
    assert is_generate_image_intent(msg) is True
    assert should_take_direct_image_path(msg, []) is True
