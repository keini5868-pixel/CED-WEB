"""Planificacion de timeline + cues Sonilo + gate Veo."""

from __future__ import annotations

import re
from typing import Any

from app.domain.video_edit_economy import VEO_MAX_PER_JOB, VEO_MAX_SECONDS

_SCENE_SPLIT = re.compile(r"\n\s*\n+|^\s*(?:\d+[\.\)]\s+|escena\s*\d+\s*[:\-])", re.I | re.M)

_STYLE_MOODS: list[tuple[str, re.Pattern[str]]] = [
    ("suspense", re.compile(r"\b(suspenso|suspense|terror|horror|misterio|tensi[oó]n)\b", re.I)),
    ("action", re.compile(r"\b(acci[oó]n|action|r[aá]pido|energia|energ[ií]a|din[aá]mico)\b", re.I)),
    ("drama", re.compile(r"\b(drama|emocional|triste|lento|cinem[aá]tico)\b", re.I)),
]


def detect_edit_mood(script: str) -> str | None:
    text = (script or "").strip()
    for mood, pattern in _STYLE_MOODS:
        if pattern.search(text):
            return mood
    return None


def _is_style_directive(script: str) -> bool:
    text = (script or "").strip()
    if not text or len(text) > 120:
        return False
    parts = [p for p in _SCENE_SPLIT.split(text) if p and p.strip()]
    if _SCENE_SPLIT.search(text) and len(parts) >= 2:
        return False
    return detect_edit_mood(text) is not None


def _paced_style_scenes(script: str, *, duration_sec: float, mood: str) -> list[dict[str, Any]]:
    dur = max(2.0, float(duration_sec))
    if mood == "suspense":
        fracs = [0.0, 0.18, 0.42, 0.58, 0.78]
        beat = max(1.2, min(6.0, dur / 5.0))
        filt = "contrast"
        effect = "zoomInSlow"
    elif mood == "action":
        fracs = [0.0, 0.22, 0.38, 0.55, 0.72, 0.88]
        beat = max(0.8, min(4.0, dur / 6.0))
        filt = "boost"
        effect = "zoomIn"
    else:
        fracs = [0.0, 0.25, 0.5, 0.75]
        beat = max(1.5, min(8.0, dur / 4.0))
        filt = "muted"
        effect = "zoomInSlow"

    scenes: list[dict[str, Any]] = []
    t_out = 0.0
    for i, frac in enumerate(fracs):
        src_start = round(min(dur - 0.5, frac * dur), 2)
        length = beat if i < len(fracs) - 1 else max(beat, dur - t_out)
        length = min(length, max(0.5, dur - src_start))
        src_end = round(src_start + length, 2)
        scenes.append(
            {
                "index": i,
                "start": src_start,
                "end": src_end,
                "text": script.strip()[:500] if i == 0 else f"Beat {i + 1} ({mood})",
                "hard_cut_after": mood == "action",
                "filter": filt,
                "effect": effect if i % 2 == 0 else "zoomOutSlow",
                "style_mood": mood,
            }
        )
        t_out += length
        if t_out >= dur - 0.1:
            break
    return scenes


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

    mood = detect_edit_mood(text)
    if _is_style_directive(text) and mood:
        return _paced_style_scenes(text, duration_sec=duration_sec, mood=mood)

    parts = [p.strip() for p in _SCENE_SPLIT.split(text) if p and p.strip()]
    if len(parts) < 2:
        parts = [s.strip() for s in re.split(r"(?<=[\.\!\?])\s+", text) if s.strip()]
    if not parts:
        parts = [text]
    if len(parts) == 1 and mood:
        return _paced_style_scenes(text, duration_sec=duration_sec, mood=mood)

    n = len(parts)
    slice_len = max(0.5, float(duration_sec) / n)
    jump_re = re.compile(
        r"\b(despu[eé]s|luego|m[aá]s tarde|en otro|mientras|corte a|flashback|transici[oó]n)\b",
        re.I,
    )
    scenes: list[dict[str, Any]] = []
    t = 0.0
    for i, part in enumerate(parts):
        end = float(duration_sec) if i == n - 1 else min(float(duration_sec), t + slice_len)
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
    cues: list[dict[str, Any]] = []
    for scene in scenes:
        if len(cues) >= max_cues:
            break
        text = str(scene.get("text") or "").strip()
        if not text:
            continue
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
    if any(w in lower for w in ("suspenso", "suspense", "terror", "misterio")):
        return "Low tense cinematic drone swell, short, suspense"
    if any(w in lower for w in ("puerta", "door", "entra")):
        return "Door open whoosh, subtle, short"
    if any(w in lower for w in ("dinero", "pago", "compra", "cash")):
        return "Soft cash register chime, short"
    if any(w in lower for w in ("exito", "éxito", "logro", "gana", "celebra")):
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
    mood = detect_edit_mood(script) or (
        str(scenes[0].get("style_mood") or "") if scenes else None
    )
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
        elif scene.get("hard_cut_after"):
            transitions.append({"type": "cut", "at": scene["end"], "duration_sec": 0})
        else:
            transitions.append({"type": "fade", "at": scene["end"], "duration_sec": 0.4})
    return {
        "version": 1,
        "provider": "shotstack",
        "style_mood": mood,
        "output": {
            "format": "mp4",
            "resolution": "1080",
            "aspect": "16:9",
            "duration_sec": round(float(duration_sec), 2),
        },
        "source": {"asset": source_asset},
        "scenes": scenes,
        "transitions": transitions,
        "sonilo": {"mode": "text_to_sfx", "cues": cues},
        "veo": veo,
        "title": {
            "enabled": bool(mood),
            "text": (script or "").strip()[:48],
            "mood": mood,
        },
    }
