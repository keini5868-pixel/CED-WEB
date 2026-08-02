"""Planificación de timeline + cues Sonilo + gate Veo (sin providers externos aún)."""

from __future__ import annotations

import re
from typing import Any

from app.domain.video_edit_economy import VEO_MAX_PER_JOB, VEO_MAX_SECONDS


_SCENE_SPLIT = re.compile(r"\n\s*\n+|^\s*(?:\d+[\.\)]\s+|escena\s*\d+\s*[:\-])", re.I | re.M)


def split_script_scenes(script: str, *, duration_sec: float) -> list[dict[str, Any]]:
    text = (script or "").strip()
    if not text:
        return [
            {
                "index": 0,
                "start": 0.0,
                "end": float(duration_sec),
                "text": "",
                "hard_cut_after": False,
            }
        ]
    parts = [p.strip() for p in _SCENE_SPLIT.split(text) if p and p.strip()]
    if len(parts) < 2:
        # Fallback: oraciones
        parts = [s.strip() for s in re.split(r"(?<=[\.\!\?])\s+", text) if s.strip()]
    if not parts:
        parts = [text]
    n = len(parts)
    slice_len = max(0.5, float(duration_sec) / n)
    jump_re = re.compile(
        r"\b(después|luego|más tarde|en otro|mientras|corte a|flashback|transición)\b",
        re.I,
    )
    scenes: list[dict[str, Any]] = []
    t = 0.0
    for i, part in enumerate(parts):
        end = float(duration_sec) if i == n - 1 else min(float(duration_sec), t + slice_len)
        # Salto brusco en el BORDE: la siguiente escena anuncia cambio de tiempo/lugar
        next_part = parts[i + 1] if i + 1 < n else ""
        hard = bool(jump_re.search(next_part)) if next_part else False
        scenes.append(
            {
                "index": i,
                "start": round(t, 2),
                "end": round(end, 2),
                "text": part[:500],
                "hard_cut_after": hard,
            }
        )
        t = end
    return scenes


def build_sonilo_text_cues(scenes: list[dict[str, Any]], *, max_cues: int = 5) -> list[dict[str, Any]]:
    """3–5 cues Text→SFX (no Video→SFX)."""
    cues: list[dict[str, Any]] = []
    for scene in scenes:
        if len(cues) >= max_cues:
            break
        text = str(scene.get("text") or "").strip()
        if not text:
            continue
        # Cue corto ~3s centrado en la escena
        start = float(scene["start"])
        end = float(scene["end"])
        mid = (start + end) / 2.0
        cue_start = max(start, mid - 1.5)
        cue_end = min(end, cue_start + 3.0)
        prompt = _sfx_prompt_from_text(text)
        cues.append(
            {
                "start": round(cue_start, 2),
                "end": round(cue_end, 2),
                "duration_sec": round(cue_end - cue_start, 2),
                "mode": "text_to_sfx",
                "prompt": prompt,
            }
        )
    # Garantizar al menos 3 si hay escenas
    while len(cues) < min(3, max(1, len(scenes))) and scenes:
        s = scenes[len(cues) % len(scenes)]
        cues.append(
            {
                "start": float(s["start"]),
                "end": min(float(s["end"]), float(s["start"]) + 2.5),
                "duration_sec": 2.5,
                "mode": "text_to_sfx",
                "prompt": "Soft whoosh transition, clean, short",
            }
        )
        if len(cues) >= 3:
            break
    return cues[:max_cues]


def _sfx_prompt_from_text(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("puerta", "door", "entra")):
        return "Door open whoosh, subtle, short"
    if any(w in lower for w in ("dinero", "pago", "compra", "cash")):
        return "Soft cash register chime, short"
    if any(w in lower for w in ("éxito", "logro", "gana", "celebra")):
        return "Uplifting soft success chime"
    if any(w in lower for w in ("noche", "oscuro", "mister")):
        return "Low ambient tension swell, short"
    return f"Subtle cinematic accent matching: {text[:80]}"


def evaluate_veo_transition(
    scenes: list[dict[str, Any]],
    *,
    veo_enabled: bool,
    user_veo_ratio_ok: bool = True,
) -> dict[str, Any]:
    """Veo Lite solo si hay salto brusco + flag + cupo. Nunca flujo estándar."""
    if not veo_enabled or not user_veo_ratio_ok:
        return {"use_veo": False, "reason": "disabled_or_quota"}
    hard_idx = next((i for i, s in enumerate(scenes) if s.get("hard_cut_after")), None)
    if hard_idx is None:
        return {"use_veo": False, "reason": "no_hard_cut"}
    a = scenes[hard_idx]
    b = scenes[hard_idx + 1] if hard_idx + 1 < len(scenes) else None
    if not b:
        return {"use_veo": False, "reason": "no_next_scene"}
    return {
        "use_veo": True,
        "tier": "veo-3.1-lite-720p",
        "max_seconds": VEO_MAX_SECONDS,
        "max_per_job": VEO_MAX_PER_JOB,
        "after_scene": a["index"],
        "before_scene": b["index"],
        "reason": "hard_cut_detected",
    }


def build_edit_timeline(
    *,
    duration_sec: float,
    script: str,
    source_asset: str,
    veo_enabled: bool = False,
) -> dict[str, Any]:
    scenes = split_script_scenes(script, duration_sec=duration_sec)
    cues = build_sonilo_text_cues(scenes, max_cues=5)
    veo = evaluate_veo_transition(scenes, veo_enabled=veo_enabled)
    transitions: list[dict[str, Any]] = []
    for i, scene in enumerate(scenes[:-1]):
        if veo.get("use_veo") and veo.get("after_scene") == scene["index"]:
            transitions.append(
                {
                    "type": "veo_lite",
                    "at": scene["end"],
                    "duration_sec": VEO_MAX_SECONDS,
                    "meta": veo,
                }
            )
        else:
            transitions.append(
                {
                    "type": "fade",
                    "at": scene["end"],
                    "duration_sec": 0.4,
                }
            )
    return {
        "version": 1,
        "provider": "shotstack",
        "output": {
            "format": "mp4",
            "resolution": "1080",
            "aspect": "9:16",
            "duration_sec": round(float(duration_sec), 2),
        },
        "source": {"asset": source_asset},
        "scenes": scenes,
        "transitions": transitions,
        "sonilo": {"mode": "text_to_sfx", "cues": cues},
        "veo": veo,
    }
