"""Overlay lock: leer el texto exacto, preguntar «¿La genero?», luego pintar."""

from __future__ import annotations

from app.modules.module_acks import MODULE_ACKS
from app.services.chat_image_generation import (
    should_generate_image_from_voice_turn,
    should_take_direct_image_path,
)
from app.services.chat_intents import assistant_offered_image_act
from app.services.image_text_ritual import (
    build_overlay_readback_reply,
    compose_confirmed_overlay_prompt,
    locked_overlay_lines,
    needs_overlay_readback,
    overlay_is_locked,
)
from app.services.voice_filler_bank import pick_voice_filler
from app.services.voice_tool_async import get_tool_acknowledgment


def test_scene_image_still_generates():
    msg = "genera una imagen de un atardecer"
    assert needs_overlay_readback(msg, []) is False
    assert should_take_direct_image_path(msg, []) is True


def test_flyer_without_copy_asks_before_generate():
    msg = "hazme un flyer de Restorate"
    assert overlay_is_locked(msg, []) is False
    assert needs_overlay_readback(msg, []) is True
    assert should_take_direct_image_path(msg, []) is False
    reply = build_overlay_readback_reply(msg, [])
    assert "Restorate — recuperación celular" in reply
    assert "De Restorate" not in reply
    assert reply.endswith("¿La genero?")
    assert "$" not in reply


def test_instagram_flyer_without_copy_asks_for_exact_words():
    msg = "hazme un flyer para Instagram"
    assert needs_overlay_readback(msg, []) is True
    assert should_take_direct_image_path(msg, []) is False
    reply = build_overlay_readback_reply(msg, [])
    assert "Para Instagram" not in reply
    assert "texto exacto" in reply.lower()


def test_yes_after_overlay_offer_generates_with_locked_line():
    history = [
        {"role": "user", "content": "hazme un flyer de Restorate"},
        {
            "role": "assistant",
            "content": (
                "En la pieza va a decir exactamente: Restorate — recuperación celular. "
                "¿La genero?"
            ),
        },
    ]
    assert assistant_offered_image_act(history) is True
    assert needs_overlay_readback("sí", history) is False
    assert should_take_direct_image_path("sí", history) is True
    prompt = compose_confirmed_overlay_prompt("sí", history)
    assert prompt is not None
    assert "Restorate — recuperación celular" in prompt
    assert "la genero" not in prompt.lower()
    assert should_generate_image_from_voice_turn("sí", "", history) is True


def test_quoted_flyer_generates_now():
    msg = 'hazme un flyer que diga "Restorate Energía"'
    assert overlay_is_locked(msg, []) is True
    assert needs_overlay_readback(msg, []) is False
    assert should_take_direct_image_path(msg, []) is True
    assert "Restorate" in locked_overlay_lines(msg, [])[0]


def test_old_bible_overlay_does_not_paint_new_carpenter_flyer():
    history = [
        {
            "role": "user",
            "content": 'hazme un flyer que diga "Buscad primeramente el reino de Dios y su justicia"',
        },
        {"role": "assistant", "content": "Listo. Aquí está tu imagen generada."},
    ]
    msg = (
        "quiero generar un flyer, la frase era, inevitablemente el tiempo va a pasar, "
        "no te dediques a perder, imagina ese carpintero hay unas herramientas"
    )
    lines = locked_overlay_lines(msg, history)
    assert overlay_is_locked(msg, history) is True
    assert needs_overlay_readback(msg, history) is False
    assert should_take_direct_image_path(msg, history) is True
    blob = " ".join(lines).lower()
    assert "tiempo va a pasar" in blob
    assert "reino de dios" not in blob
    assert "carpintero" not in blob


def test_esta_frase_without_quotes_generates_now():
    msg = (
        "quiero generar un flyer de fondo oscuro que tenga escrito esta frase "
        "la credibilidad incumplida es como un bacon que te cobra una deuda "
        "con intereses dobles"
    )
    lines = locked_overlay_lines(msg, [])
    assert overlay_is_locked(msg, []) is True
    assert needs_overlay_readback(msg, []) is False
    assert should_take_direct_image_path(msg, []) is True
    assert lines
    assert "credibilidad incumplida" in lines[0].lower()
    assert "bacon" in lines[0].lower()


def test_cartel_in_scene_is_not_overlay_ritual():
    msg = "Ok, genera la imagen: Sek en un traje negro rompiendo un cartel de Instagram"
    assert needs_overlay_readback(msg, []) is False
    assert should_take_direct_image_path(msg, []) is True


def test_en_texto_with_labels_is_locked():
    msg = (
        "generame una imagen de un mapa holográfico digital con las etiquetas "
        "sistema avanzado, análisis profundo EN TEXTO"
    )
    assert overlay_is_locked(msg, []) is True
    assert needs_overlay_readback(msg, []) is False
    assert should_take_direct_image_path(msg, []) is True


def test_spoken_copy_without_quotes_locks_overlay():
    msg = (
        "genera un flyer con fondo oscuro y el texto "
        "Inevitablemente el tiempo va a pasar, no te dediques a perderlo "
        "en azul cian con sombra blanca opaca"
    )
    assert overlay_is_locked(msg, []) is True
    assert needs_overlay_readback(msg, []) is False
    assert should_take_direct_image_path(msg, []) is True


def test_missing_image_followup_generates_the_same_brief():
    from app.services.chat_image_generation import effective_user_prompt
    from app.services.chat_intents import user_insists_on_pending_image

    original = (
        "genera un flyer con fondo oscuro y el texto "
        "'Inevitablemente el tiempo va a pasar, no te dediques a perderlo' "
        "en azul cian"
    )
    history = [
        {"role": "user", "content": original},
        {
            "role": "assistant",
            "content": "En la pieza va a decir exactamente: Inevitablemente el tiempo. ¿La genero?",
        },
    ]
    follow = "no había visto la imagen, genérame el flyer"
    assert user_insists_on_pending_image(follow, history) is True
    assert needs_overlay_readback(follow, history) is False
    assert should_take_direct_image_path(follow, history) is True
    assert "Inevitablemente" in (effective_user_prompt(follow, history) or "")
    assert user_insists_on_pending_image("genérame el flyer", history) is True
    assert "Inevitablemente" in (
        effective_user_prompt("genérame el flyer", history) or ""
    )


def test_marketing_flyer_with_brand_is_not_pending_insist():
    from app.services.chat_intents import user_insists_on_pending_image

    history = [
        {"role": "user", "content": "analiza esta imagen"},
        {
            "role": "assistant",
            "content": "Flyer promocional DUGLE STUDIO. Precios $49 / $79 / $99.",
        },
    ]
    assert (
        user_insists_on_pending_image(
            "genera creativo estilo flyer con DUGLE STUDIO", history
        )
        is False
    )
    assert (
        user_insists_on_pending_image(
            'genera flyer "DUGLE STUDIO" con precios $49 $79 $99', history
        )
        is False
    )


def test_voice_args_prompt_locks_overlay_even_if_heard_is_thin():
    llm_prompt = (
        'Flyer de fondo oscuro con el texto "Inevitablemente el tiempo va a pasar, '
        'no te dediques a perderlo" en azul cian'
    )
    raw_user = "hazme un flyer"
    assert overlay_is_locked(llm_prompt, []) is True
    assert needs_overlay_readback(raw_user, []) is True
    copy_already_locked = overlay_is_locked(llm_prompt, []) or overlay_is_locked(
        raw_user, []
    )
    assert copy_already_locked is True


def test_idea_talk_is_not_overlay_ritual():
    msg = "tengo una idea para un flyer de Instagram"
    assert needs_overlay_readback(msg, []) is False
    assert should_take_direct_image_path(msg, []) is False


def test_voice_image_filler_is_va():
    assert MODULE_ACKS["image_gen"] == "Va."
    assert get_tool_acknowledgment("generate_image") == "Va."
    filler = pick_voice_filler("module", call_id="test-overlay", module="image_gen")
    assert filler in {"Va.", "Un momento."}
    assert "generando" not in filler.lower()
