"""Orquestador de imagen: copy vs escena, y corrección sobre la misma pieza."""

from __future__ import annotations

from app.services.chat_image_generation import pick_voice_image_source_prompt
from app.services.chat_intents import (
    is_image_subject_correction,
    user_keeps_same_image_piece,
    user_requests_new_image_piece,
    wants_image_reference_edit,
)
from app.services.copy_quality import (
    extract_locked_slogan,
    is_scene_instruction_caption,
    user_asks_for_on_image_copy,
    user_requests_overlay_correction,
)
from app.services.image_overlay_orchestrator import (
    enforce_overlay_fix_prompt,
    plan_image_generation,
)
from app.services.image_text_ritual import locked_overlay_lines


CASTLE_STT = (
    "generame una imagen de azul oscuro con un fondo azul oscuro y un castillo "
    "en la digital antigua pero digital con una puerta grande donde vaya luz "
    "redondo de CED y afuera que hay en la tierra donde está el frente del "
    "castillo ponga Inevitablemente el tiempo va a pasar no te dediques a perder"
)

OVERLAY_FIX = (
    "me parece genial pero la imagen quedó mal quiero que la corrijas el escrito "
    "que tiene ahí la frase quiero que ahí vaya inevitablemente el tiempo va a "
    "pasar no te dediques a perder"
)

CASTLE_HISTORY = [
    {"role": "user", "content": CASTLE_STT},
    {"role": "assistant", "content": "Listo, señor. Ya puede verla en pantalla."},
]


def test_voice_stt_locks_slogan_not_tierra():
    lines = locked_overlay_lines(CASTLE_STT, [])
    blob = " ".join(lines).casefold()
    assert "inevitablemente el tiempo va a pasar" in blob
    assert "no te dediques a perder" in blob
    assert "tierra" not in blob
    assert is_scene_instruction_caption("Tierra Tierra") is True
    assert user_requests_new_image_piece(CASTLE_STT, []) is True
    assert wants_image_reference_edit(CASTLE_STT) is False


def test_overlay_correction_keeps_same_castle():
    assert user_requests_overlay_correction(OVERLAY_FIX) is True
    assert is_image_subject_correction(OVERLAY_FIX) is False
    assert user_requests_new_image_piece(OVERLAY_FIX, CASTLE_HISTORY) is False
    assert wants_image_reference_edit(OVERLAY_FIX) is True
    assert user_keeps_same_image_piece(OVERLAY_FIX, CASTLE_HISTORY) is True
    assert user_asks_for_on_image_copy(OVERLAY_FIX) is True
    lines = locked_overlay_lines(OVERLAY_FIX, CASTLE_HISTORY)
    blob = " ".join(lines).casefold()
    assert "inevitablemente el tiempo va a pasar" in blob
    assert "no te dediques a perder" in blob
    assert "tierra" not in blob


def test_extract_locked_slogan_completes_half_phrase():
    half = "abajo inevitablemente el tiempo va a pasar"
    slogan = extract_locked_slogan(half)
    assert slogan is not None
    assert "no te dediques a perder" in slogan.casefold()


def test_orchestrator_keeps_castle_when_haiku_invents_a_person():
    plan = plan_image_generation(OVERLAY_FIX, CASTLE_HISTORY)
    assert plan.overlay_fix is True
    assert plan.new_piece is False
    assert plan.keep_same_scene is True
    assert plan.use_user_utterance is True
    blob = " ".join(plan.locked_copy).casefold()
    assert "inevitablemente el tiempo va a pasar" in blob
    assert "no te dediques a perder" in blob
    assert "tierra" not in blob

    heard = OVERLAY_FIX
    haiku = "un hombre con capa amarilla de bruja en tierra tierra el tiempo va a pasar"
    chosen = pick_voice_image_source_prompt(args_prompt=haiku, heard=heard)
    assert chosen == heard
    assert "bruja" not in chosen.casefold()

    prompt = enforce_overlay_fix_prompt(
        user_text=OVERLAY_FIX,
        prior_prompt=CASTLE_STT,
        locked_copy=plan.locked_copy,
        has_reference=True,
        history=CASTLE_HISTORY,
    )
    low = prompt.casefold()
    assert "same scene" in low or "misma" in low
    assert "inevitablemente el tiempo va a pasar" in low
    assert "no te dediques a perder" in low
    assert "bruja" not in low
    assert "do not invent a person" in low
