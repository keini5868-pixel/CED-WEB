"""Adaptador directo de prompts de imagen (sin orquestador pesado)."""

from __future__ import annotations

from app.services.copy_quality import (
    build_direct_image_prompt,
    prompt_requires_ideogram_text,
)
from app.services.gemini_images import prepare_image_prompt


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


def test_chat_image_generation_wires_direct_adapter():
    """Chat/avanzado/voz: run_chat_image_generation usa build_direct_image_prompt."""
    import inspect

    from app.services import chat_image_generation as cig

    src = inspect.getsource(cig.run_chat_image_generation)
    assert "build_direct_image_prompt" in src
    assert 'context=""' in src or "context=\"\"" in src
