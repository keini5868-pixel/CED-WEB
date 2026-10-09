"""Orquestador de imagen: copy literal vs escena, y correcciones sobre la misma pieza."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.chat_intents import (
    last_concrete_image_user_prompt,
    user_keeps_same_image_piece,
    user_requests_new_image_piece,
    user_requests_prior_reference,
)
from app.services.copy_quality import (
    _NO_SCENE_CAPTIONS,
    _VISIBLE_COPY_ONLY,
    extract_locked_slogan,
    format_verbatim_image_copy,
    is_scene_instruction_caption,
    user_requests_overlay_correction,
)
from app.services.image_text_ritual import locked_overlay_lines

_SAME_SCENE_LOCK = (
    "Keep the SAME scene exactly: same castle or building, same door, "
    "same round CED mark, same dark-blue lighting and composition. "
    "Do NOT invent a person, witch, animal, or a different place. "
    "ONLY replace the painted letters with the exact Spanish sentence. "
)


@dataclass(frozen=True)
class ImageGenPlan:
    overlay_fix: bool
    new_piece: bool
    keep_same_scene: bool
    use_user_utterance: bool
    locked_copy: tuple[str, ...]


def plan_image_generation(
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> ImageGenPlan:
    """Decide si es pieza nueva o corrección de escrito, y qué copy pintar."""
    overlay_fix = user_requests_overlay_correction(user_text)
    keep_same = overlay_fix or user_keeps_same_image_piece(user_text, history)
    new_piece = (not overlay_fix) and (
        user_requests_new_image_piece(user_text, history)
        and not user_requests_prior_reference(user_text)
        and not keep_same
    )
    lines = [
        ln
        for ln in locked_overlay_lines(user_text, history)
        if not is_scene_instruction_caption(ln)
    ]
    slogan = extract_locked_slogan(user_text)
    if slogan and slogan not in lines:
        lines = [slogan, *[ln for ln in lines if ln.casefold() != slogan.casefold()]]
    return ImageGenPlan(
        overlay_fix=overlay_fix,
        new_piece=new_piece,
        keep_same_scene=keep_same or overlay_fix,
        use_user_utterance=overlay_fix or keep_same,
        locked_copy=tuple(lines),
    )


def enforce_overlay_fix_prompt(
    *,
    user_text: str,
    prior_prompt: str = "",
    locked_copy: list[str] | tuple[str, ...] | None = None,
    has_reference: bool = False,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Prompt que obliga a editar el escrito, no a inventar otra escena."""
    plan = plan_image_generation(user_text, history)
    lines = list(locked_copy or plan.locked_copy)
    verbatim = format_verbatim_image_copy(lines) if lines else ""
    prior = (prior_prompt or last_concrete_image_user_prompt(history) or "").strip()
    lead = (
        "Edit the attached photo. "
        if has_reference
        else "Recreate the previous image. "
    )
    parts = [f"{lead}{_SAME_SCENE_LOCK}", _NO_SCENE_CAPTIONS, _VISIBLE_COPY_ONLY]
    if prior and not has_reference:
        parts.append(f"Previous scene to keep: {prior[:900]}")
    if verbatim:
        parts.append(verbatim)
    return " ".join(p for p in parts if p).strip()[:3800]
