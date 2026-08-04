"""Cliente Sonilo Text→SFX (api.sonilo.com)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_BASE = "https://api.sonilo.com/v1"
_POLL_INTERVAL = 2.5
_MAX_WAIT = 90.0


def sonilo_configured() -> bool:
    return bool(_api_key())


def _api_key() -> str:
    settings = get_settings()
    key = (getattr(settings, "sonilo_api_key", None) or "").strip()
    if key:
        return key
    # Aliases comunes si Railway usó otro nombre
    import os

    for name in ("SONILO_API_KEY", "SONILO_KEY", "SONILO_TOKEN"):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Accept": "application/json",
    }


def generate_sfx_url(prompt: str, *, duration_sec: float = 2.0) -> str | None:
    """Genera SFX y devuelve URL pública, o None si falla (no tumba el render)."""
    if not sonilo_configured():
        return None
    prompt = (prompt or "").strip()[:500]
    if not prompt:
        return None
    duration = max(1, min(12, int(round(float(duration_sec)))))
    try:
        with httpx.Client(timeout=45.0) as client:
            submit = client.post(
                f"{_BASE}/text-to-sfx",
                headers=_headers(),
                files={
                    "prompt": (None, prompt),
                    "duration": (None, str(duration)),
                    "audio_format": (None, "mp3"),
                },
            )
            if submit.status_code >= 400:
                logger.warning(
                    "[SONILO] submit HTTP %s: %s",
                    submit.status_code,
                    submit.text[:300],
                )
                return None
            task_id = str((submit.json() or {}).get("task_id") or "").strip()
            if not task_id:
                logger.warning("[SONILO] submit sin task_id: %s", submit.text[:200])
                return None

            deadline = time.monotonic() + _MAX_WAIT
            while time.monotonic() < deadline:
                poll = client.get(
                    f"{_BASE}/tasks/{task_id}",
                    headers=_headers(),
                )
                if poll.status_code >= 400:
                    logger.warning(
                        "[SONILO] poll HTTP %s: %s",
                        poll.status_code,
                        poll.text[:200],
                    )
                    return None
                task = poll.json() or {}
                status = str(task.get("status") or "")
                if status in {"succeeded", "success", "done", "completed"}:
                    audio = task.get("audio") or {}
                    url = str(
                        audio.get("url")
                        or task.get("url")
                        or (task.get("result") or {}).get("url")
                        or ""
                    ).strip()
                    if url:
                        logger.info("[SONILO] sfx ready task=%s", task_id[:8])
                        return url
                    logger.warning("[SONILO] succeeded sin url: %s", str(task)[:300])
                    return None
                if status in {"failed", "error", "cancelled"}:
                    logger.warning(
                        "[SONILO] task failed: %s",
                        str(task.get("error") or task)[:300],
                    )
                    return None
                time.sleep(_POLL_INTERVAL)
            logger.warning("[SONILO] timeout task=%s", task_id[:8])
            return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("[SONILO] generate_sfx failed: %s", exc)
        return None


def resolve_cues_to_audio_clips(
    cues: list[dict[str, Any]],
    *,
    max_cues: int = 4,
) -> list[dict[str, Any]]:
    """Planifica cues → clips Shotstack audio (src URL). Fallos se omiten."""
    clips: list[dict[str, Any]] = []
    for cue in (cues or [])[:max_cues]:
        if not isinstance(cue, dict):
            continue
        prompt = str(cue.get("prompt") or "").strip()
        if not prompt:
            continue
        start = float(cue.get("start") or 0)
        dur = float(cue.get("duration_sec") or 2.0)
        dur = max(1.0, min(6.0, dur))
        url = generate_sfx_url(prompt, duration_sec=dur)
        if not url:
            continue
        clips.append(
            {
                "asset": {
                    "type": "audio",
                    "src": url,
                    "volume": 0.85,
                },
                "start": round(max(0.0, start), 3),
                "length": round(dur, 3),
            }
        )
    return clips
