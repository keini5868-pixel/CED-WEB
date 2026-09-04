"""Expander estrecho de escena — director de arte, no el LLM de chat.

Enriquece iluminación/composición. Nunca sustituye la política de texto:
`build_direct_image_prompt` sigue mandando NONE / DECORATIVE / LITERAL.
Timeout corto: si falla, el path directo usa el ancla.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

logger = logging.getLogger(__name__)

EXPANDER_TIMEOUT_SEC = 2.0
EXPANDER_MAX_TOKENS = 500

_EXPANDER_SYSTEM = """You are CED's art director for image-generation prompts. Your only job is to enrich lighting, composition, materials and atmosphere of the given ANCHOR scene.

Hard rules:
- Do not chat, greet, or use markdown.
- Do not change the subject. If the anchor is an eagle, the output is an eagle. No robots or HUD unless the anchor asks for them.
- Do not invent slogans, CTAs, or commercial copy. If text is not quoted in the anchor, it does not exist.
- CED dark cyan HUD atmosphere is opt-in: only if the anchor or visual thread names CED / Castillo / holographic CED assistant.
- Output one plain continuous English paragraph (scene direction). Keep any quoted overlay text in the user's original language, unchanged.
- Text mode NONE: cinematic photography, no letters, no UI.
- Text mode DECORATIVE: hologram/HUD/interface may have illegible micro-glyphs, not marketing headlines.
- Text mode LITERAL: keep quoted copy exact; you may describe layout and lighting only.
"""

_PREAMBLE = re.compile(
    r"(?is)^\s*(?:here(?:'s| is)(?: the)?(?: prompt)?|aquí tienes(?: el prompt)?|"
    r"prompt\s*:)\s*[:.\-]*\s*"
)
_FENCE = re.compile(r"(?is)^```(?:\w+)?\s*|\s*```$")


def _clean_expander_output(raw: str) -> str:
    t = _FENCE.sub("", (raw or "").strip()).strip()
    t = _PREAMBLE.sub("", t).strip()
    t = t.strip("\"'`")
    return re.sub(r"\s+", " ", t).strip()


def _build_user_payload(anchor: str, visual_thread: str, text_mode: str) -> str:
    thread = (visual_thread or "").strip()[:1800]
    parts = [
        f"Text mode: {text_mode.upper()}",
        f"Anchor:\n{(anchor or '').strip()[:2500]}",
    ]
    if thread:
        parts.append(f"Recent visual thread (this piece only):\n{thread}")
    parts.append("Write the enriched scene paragraph now.")
    return "\n\n".join(parts)


def _call_gemini_flash(user_payload: str) -> str:
    from google import genai
    from google.genai import types

    from app.config import get_settings

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return ""
    model = (settings.gemini_voice_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=f"{_EXPANDER_SYSTEM}\n\n{user_payload}",
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=EXPANDER_MAX_TOKENS,
        ),
    )
    return (getattr(response, "text", None) or "").strip()


def expand_image_scene(
    anchor: str,
    visual_thread: str = "",
    text_mode: str = "none",
) -> tuple[str | None, str]:
    """Devuelve (escena enriquecida | None, hit|timeout|error|skip)."""
    from app.config import get_settings

    base = (anchor or "").strip()
    if not base:
        return None, "skip"
    if not get_settings().google_api_key.strip():
        return None, "skip"

    payload = _build_user_payload(base, visual_thread, text_mode)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(_call_gemini_flash, payload)
        raw = fut.result(timeout=EXPANDER_TIMEOUT_SEC)
    except FutureTimeout:
        logger.warning("[IMG-EXPANDER] timeout=%.1fs", EXPANDER_TIMEOUT_SEC)
        return None, "timeout"
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IMG-EXPANDER] error=%s", str(exc)[:160])
        return None, "error"
    finally:
        pool.shutdown(wait=False)

    cleaned = _clean_expander_output(raw)
    if len(cleaned) < 48:
        return None, "error"
    if re.search(r"(?i)aquí tienes|here is the prompt", cleaned):
        return None, "error"
    return cleaned[:2200], "hit"
