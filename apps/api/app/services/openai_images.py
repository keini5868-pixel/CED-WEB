"""DEPRECATED — usar app.services.gemini_images.generate_image exclusivamente."""

from __future__ import annotations

import logging
import warnings
from typing import Any

logger = logging.getLogger(__name__)

STD_COST_USD = 0.04
HD_COST_USD = 0.08


def _day_image_counts(user_id: str) -> tuple[int, int]:
    from app.services.gemini_images import _day_image_counts as _counts

    return _counts(user_id)


def generate_image(
    *,
    user_id: str,
    plan_id: str | None,
    prompt: str,
    quality: str | None = "auto",
) -> dict[str, Any]:
    warnings.warn(
        "openai_images.generate_image is deprecated; use gemini_images.generate_image",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.warning("[OPENAI:IMAGE] deprecated module — redirecting to gemini_images")
    from app.services.gemini_images import generate_image as generate_image_gemini_only

    return generate_image_gemini_only(
        user_id=user_id,
        plan_id=plan_id,
        prompt=prompt,
        quality=quality,
    )
