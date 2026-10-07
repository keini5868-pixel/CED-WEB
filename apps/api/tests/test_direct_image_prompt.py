"""Adaptador directo de prompts de imagen (sin orquestador pesado)."""

from __future__ import annotations

from app.services.copy_quality import (
    build_direct_image_prompt,
    prompt_requires_ideogram_text,
)
from app.services.gemini_images import prepare_image_prompt


def test_activize_original_jar_is_locked_not_generic():
    from app.services.copy_quality import (
        build_reference_scene_edit_prompt,
        lock_spanish_image_subject,
        official_brand_likeness_note,
    )

    locked = lock_spanish_image_subject(
        "persona con un frazco de activize en la mano pero el frasco sea el original"
    )
    low = locked.lower()
    assert "frasco de activize" in low
    assert "official" in low or "retail jar" in low
    assert "not a boat" in low
    note = official_brand_likeness_note("quiero que el frasco sea el original")
    assert note is not None
    assert "oficial" in note.lower() or "look oficial" in note.lower()
    bg = build_reference_scene_edit_prompt("ponle un fondo azul")
    assert "castle/building" not in bg
    assert "same person" in bg or "same subject" in bg.lower()


def test_bote_de_creatina_is_a_tub_not_a_boat():
    from app.services.copy_quality import lock_spanish_image_subject

    locked = lock_spanish_image_subject(
        "hombre musculoso con un bote de creatina en la mano"
    )
    low = locked.lower()
    assert "bote de creatina" in low
    assert "not a boat" in low
    assert "subject lock" in low
    brief = build_direct_image_prompt(
        "genera un hombre musculoso con un envase de creatina en su mano",
        visual_override="A cinematic ship helm at sunset, nautical deck.",
    )
    prompt = str(brief["prompt"]).lower()
    assert "creatina" in prompt
    assert "envase" in prompt or "bote" in prompt
    assert "do not change the subject" in prompt
    assert "ship helm" in prompt  # lighting leftover is ok
    assert prompt.index("creatina") < prompt.index("ship helm")


def test_direct_scene_keeps_user_subject_no_ced_no_textos():
    msg = "generame una imagen de un hombre recostado de un arbol en un atardecer"
    direct = build_direct_image_prompt(msg)
    prompt = direct["prompt"].lower()
    assert "hombre" in prompt and "atardecer" in prompt
    assert "sistema ced" not in prompt
    assert "textos exactos" not in prompt
    assert "photorealistic scene depicting" not in prompt
    assert direct["wants_literal_text"] is False
    assert "no text, letters" in prompt
    assert "full frame" in prompt
    assert "spelling:" not in prompt


def test_direct_en_texto_holographic_map_keeps_labels_in_natural_language():
    msg = (
        "Okay GENERA UNA IMAGEN DE un mapa holográfico digital donde pongas las "
        "características que te nombraré sistema avanzado análisis profundo "
        "asistente con voz estilo jarvis y publicación en redes EN TEXTO"
    )
    assert prompt_requires_ideogram_text(msg) is True
    direct = build_direct_image_prompt(msg)
    assert direct["wants_literal_text"] is True
    p = direct["prompt"]
    low = p.lower()
    scene = direct["visual_brief"].lower()
    assert "mapa" in scene and "hologr" in scene
    assert "sistema avanzado" in scene
    assert "análisis profundo" in scene or "analisis profundo" in scene
    assert "jarvis" in scene
    assert "publicación en redes" in scene or "publicacion en redes" in scene
    assert "include the requested labels" in low
    assert not scene.startswith("okay")
    assert "genera una imagen" not in scene
    assert "TEXTOS EXACTOS" not in p
    prepared = prepare_image_prompt(p, "robot corriendo a toda velocidad HOLA")
    assert "robot corriendo" not in prepared.lower()
    assert prepared == p or prepared.startswith(p[:80])


def test_direct_ignores_history_context_to_avoid_theme_mixing():
    msg = "un águila volando sobre un cielo lluvioso"
    direct = build_direct_image_prompt(
        msg,
        context="Okay genera un robot corriendo. Sistema CED. HOLA",
    )
    low = direct["prompt"].lower()
    assert "águila" in low or "aguila" in low
    assert "robot" not in low
    assert "sistema ced" not in low
    assert "hola" not in low


def test_prepare_image_prompt_no_longer_merges_chat_history():
    prepared = prepare_image_prompt(
        "un atardecer en la playa",
        "Fitline Basics es un complemento. Robot corriendo a toda velocidad.",
    )
    low = prepared.lower()
    assert "atardecer" in low and "playa" in low
    assert "fitline" not in low
    assert "robot" not in low
    assert "textos exactos" not in low


def test_literal_flyer_locks_shadow_punctuation_and_no_people():
    msg = (
        "genera un flyer con fondo oscuro y el texto "
        "'Inevitablemente el tiempo va a pasar, no te dediques a perderlo' "
        "en azul cian con sombra blanca opaca"
    )
    direct = build_direct_image_prompt(msg)
    prompt = str(direct["prompt"])
    low = prompt.lower()
    assert direct["wants_literal_text"] is True
    assert "Inevitablemente el tiempo va a pasar, no te dediques a perderlo" in prompt
    assert "," in prompt
    assert "sombra blanca" in low or "shadow must be white" in low
    assert "not cyan" in low
    assert "same font weight" in low or "one typeface" in low
    assert "sin personas" in low or "no people" in low


def test_chat_image_generation_wires_direct_adapter():
    """Chat/avanzado/voz: run_chat_image_generation usa build_direct_image_prompt."""
    import inspect

    from app.services import chat_image_generation as cig

    src = inspect.getsource(cig.run_chat_image_generation)
    assert "build_direct_image_prompt" in src
    assert "visual_override" in src
    assert "expand_image_scene" in src
