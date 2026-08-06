"""Cliente Shotstack Edit + Ingest (stage/v1)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_UPLOAD_TIMEOUT = 180.0
_POLL_INTERVAL = 3.0
_INGEST_MAX_WAIT = 180.0
_RENDER_MAX_WAIT = 480.0


def _env() -> str:
    settings = get_settings()
    env = (getattr(settings, "shotstack_env", None) or "stage").strip().lower()
    return "v1" if env == "v1" else "stage"


def _api_key() -> str:
    return (get_settings().shotstack_api_key or "").strip()


def shotstack_configured() -> bool:
    return bool(_api_key())


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "x-api-key": _api_key(),
    }


def _ingest_base() -> str:
    return f"https://api.shotstack.io/ingest/{_env()}"


def _edit_base() -> str:
    return f"https://api.shotstack.io/edit/{_env()}"


def request_upload_url(*, filename: str = "source.mp4") -> dict[str, str]:
    """POST /upload → signed URL + source id."""
    with httpx.Client(timeout=30.0) as client:
        # Body vacío es el path documentado; filename ayuda a tipos no-binarios.
        headers = {**_headers()}
        kwargs: dict[str, Any] = {"headers": headers}
        if filename and filename.lower() not in {"source.mp4", "video.mp4", "upload.mp4"}:
            headers["Content-Type"] = "application/json"
            kwargs["json"] = {"filename": filename}
        res = client.post(f"{_ingest_base()}/upload", **kwargs)
        if res.status_code >= 400:
            raise RuntimeError(
                f"Shotstack upload URL HTTP {res.status_code}: {res.text[:300]}"
            )
        data = res.json().get("data") or {}
        attrs = data.get("attributes") or {}
        source_id = str(attrs.get("id") or data.get("id") or "").strip()
        url = str(attrs.get("url") or "").strip()
        if not source_id or not url:
            raise RuntimeError(f"Shotstack upload: respuesta sin id/url: {res.text[:300]}")
        return {"source_id": source_id, "upload_url": url}


def put_bytes_to_signed_url(
    upload_url: str,
    content: bytes,
    *,
    content_type: str = "video/mp4",
) -> None:
    # No enviar headers extra en PUT firmado (S3 SignatureDoesNotMatch).
    # Content-Type solo si hace falta (texto/SRT); video se detecta solo.
    headers: dict[str, str] = {}
    ct = (content_type or "").strip().lower()
    if ct and not ct.startswith("video/") and ct not in {"application/octet-stream", ""}:
        headers["Content-Type"] = content_type
    with httpx.Client(timeout=_UPLOAD_TIMEOUT) as client:
        res = client.put(
            upload_url,
            content=content,
            headers=headers if headers else {},
        )
        if res.status_code >= 400:
            raise RuntimeError(
                f"Shotstack PUT upload falló HTTP {res.status_code}: {res.text[:200]}"
            )


def wait_source_ready(source_id: str) -> str:
    """Poll ingest source until ready; return public source URL."""
    meta = wait_source_meta(source_id)
    return meta["source_url"]


def wait_source_meta(source_id: str) -> dict[str, Any]:
    """Poll ingest until ready; return url + dimensions."""
    deadline = time.monotonic() + _INGEST_MAX_WAIT
    last_status = ""
    with httpx.Client(timeout=30.0) as client:
        while time.monotonic() < deadline:
            res = client.get(
                f"{_ingest_base()}/sources/{source_id}",
                headers=_headers(),
            )
            res.raise_for_status()
            attrs = ((res.json().get("data") or {}).get("attributes") or {})
            last_status = str(attrs.get("status") or "")
            if last_status == "ready":
                src = str(attrs.get("source") or "").strip()
                if not src:
                    raise RuntimeError("Shotstack source ready sin URL")
                width = attrs.get("width")
                height = attrs.get("height")
                try:
                    width_i = int(width) if width is not None else None
                except (TypeError, ValueError):
                    width_i = None
                try:
                    height_i = int(height) if height is not None else None
                except (TypeError, ValueError):
                    height_i = None
                return {
                    "source_url": src,
                    "width": width_i,
                    "height": height_i,
                    "duration": attrs.get("duration"),
                }
            if last_status == "failed":
                raise RuntimeError("Shotstack ingest falló al procesar el video")
            time.sleep(_POLL_INTERVAL)
    raise TimeoutError(f"Shotstack ingest timeout (último status={last_status})")


def upload_video_bytes(
    content: bytes,
    *,
    filename: str = "source.mp4",
    content_type: str = "video/mp4",
) -> dict[str, str]:
    meta = request_upload_url(filename=filename)
    put_bytes_to_signed_url(
        meta["upload_url"], content, content_type=content_type
    )
    source_url = wait_source_ready(meta["source_id"])
    return {
        "source_id": meta["source_id"],
        "source_url": source_url,
    }


def timeline_to_shotstack_edit(
    *,
    source_url: str,
    timeline: dict[str, Any],
    duration_sec: float,
    audio_clips: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convierte timeline CED → Edit API.

    - fit=contain evita recortar caras/cuerpos
    - Cortes duros insertan flash negro corto (se nota la edición)
    - audio_clips: SFX Sonilo (u otros) en track aparte
    """
    from app.services.video_edit_pilot.timeline import aspect_from_dimensions

    scenes = list(timeline.get("scenes") or [])
    fit = str((timeline.get("output") or {}).get("fit") or "contain")
    if fit not in {"contain", "cover", "crop", "none"}:
        fit = "contain"
    clips: list[dict[str, Any]] = []
    flash_clips: list[dict[str, Any]] = []
    cursor = 0.0
    flash_len = 0.12

    def _video_clip(start_src: float, length: float, start_out: float) -> dict[str, Any]:
        return {
            "asset": {
                "type": "video",
                "src": source_url,
                "trim": round(start_src, 3),
                "volume": 0.9,
            },
            "start": round(start_out, 3),
            "length": round(length, 3),
            "fit": fit,
            "scale": 1,
            "position": "center",
        }

    if not scenes:
        clips.append(_video_clip(0.0, max(0.5, float(duration_sec)), 0.0))
    else:
        for i, scene in enumerate(scenes):
            start_src = float(scene.get("start") or 0)
            end_src = float(scene.get("end") or start_src)
            length = max(0.2, end_src - start_src)
            clip = _video_clip(start_src, length, cursor)
            filt = str(scene.get("filter") or "").strip()
            if filt in {"boost", "contrast", "darken", "greyscale", "lighten", "muted"}:
                clip["filter"] = filt

            t_out = str(scene.get("transition_out") or "")
            if not t_out:
                for t in timeline.get("transitions") or []:
                    if not isinstance(t, dict):
                        continue
                    if abs(float(t.get("at") or 0) - end_src) < 0.08:
                        t_out = str(t.get("type") or "fade")
                        break
            is_last = i >= len(scenes) - 1
            if not is_last:
                if t_out == "cut":
                    # Flash negro breve = corte visible en guiones lineales 0-8→8-18
                    edge = round(cursor + length, 3)
                    flash_clips.append(
                        {
                            "asset": {
                                "type": "title",
                                "text": " ",
                                "style": "minimal",
                                "color": "#000000",
                                "background": "#000000",
                                "position": "center",
                                "size": "x-large",
                            },
                            "start": edge,
                            "length": flash_len,
                            "fit": "cover",
                            "position": "center",
                            "scale": 1,
                        }
                    )
                    cursor = edge + flash_len
                else:
                    clip["transition"] = {"out": "fadeSlow"}
                    cursor += length
            else:
                cursor += length
            clips.append(clip)

    tracks: list[dict[str, Any]] = [{"clips": clips}]
    if flash_clips:
        tracks.append({"clips": flash_clips})

    # SFX Sonilo / audio externo
    sfx = [c for c in (audio_clips or []) if isinstance(c, dict) and c.get("asset")]
    if sfx:
        tracks.append({"clips": sfx})

    title = timeline.get("title") or {}
    if title.get("enabled") and title.get("text"):
        label = str(title.get("text") or "").strip()[:40]
        tracks.append(
            {
                "clips": [
                    {
                        "asset": {
                            "type": "title",
                            "text": label.upper(),
                            "style": "minimal",
                            "color": "#ffffff",
                            "size": "small",
                            "background": "#000000",
                            "position": "bottom",
                        },
                        "start": 0,
                        "length": min(2.0, max(1.0, float(duration_sec) * 0.06)),
                        "transition": {"in": "fade", "out": "fade"},
                    }
                ]
            }
        )

    output = timeline.get("output") or {}
    src = timeline.get("source") or {}
    aspect = str(output.get("aspect") or "").strip()
    if aspect not in {"16:9", "9:16", "1:1", "4:5"}:
        aspect = aspect_from_dimensions(src.get("width"), src.get("height"))
    return {
        "timeline": {"background": "#000000", "tracks": tracks},
        "output": {
            "format": "mp4",
            "resolution": "hd",
            "aspectRatio": aspect,
            "fps": 30,
        },
    }



def submit_render(edit_payload: dict[str, Any]) -> str:
    with httpx.Client(timeout=60.0) as client:
        res = client.post(
            f"{_edit_base()}/render",
            headers={**_headers(), "Content-Type": "application/json"},
            json=edit_payload,
        )
        if res.status_code >= 400:
            raise RuntimeError(
                f"Shotstack render HTTP {res.status_code}: {res.text[:300]}"
            )
        body = res.json()
        render_id = str(
            ((body.get("response") or {}).get("id"))
            or ((body.get("data") or {}).get("id"))
            or ""
        ).strip()
        if not render_id:
            # Edit API classic shape: {"success":true,"message":"...","response":{"id":"..."}}
            raise RuntimeError(f"Shotstack render sin id: {body}")
        return render_id


def wait_render_done(render_id: str) -> str:
    """Poll edit render until done; return video URL."""
    deadline = time.monotonic() + _RENDER_MAX_WAIT
    last_status = ""
    with httpx.Client(timeout=30.0) as client:
        while time.monotonic() < deadline:
            res = client.get(
                f"{_edit_base()}/render/{render_id}",
                headers=_headers(),
            )
            res.raise_for_status()
            body = res.json()
            response = body.get("response") or body.get("data") or {}
            if isinstance(response, dict) and "attributes" in response:
                attrs = response.get("attributes") or {}
                last_status = str(attrs.get("status") or "")
                url = str(attrs.get("url") or "").strip()
            else:
                last_status = str(response.get("status") or "")
                url = str(response.get("url") or "").strip()
            if last_status == "done" and url:
                return url
            if last_status in {"failed", "error"}:
                raise RuntimeError(f"Shotstack render falló: {last_status}")
            time.sleep(_POLL_INTERVAL)
    raise TimeoutError(f"Shotstack render timeout (último status={last_status})")


def render_video_from_bytes(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    timeline: dict[str, Any],
    duration_sec: float,
) -> dict[str, Any]:
    """Upload → wait ingest → submit edit → wait URL."""
    if not shotstack_configured():
        raise RuntimeError("SHOTSTACK_API_KEY no configurada")
    uploaded = upload_video_bytes(
        content, filename=filename, content_type=content_type or "video/mp4"
    )
    return render_video_from_source(
        source_id=uploaded["source_id"],
        source_url=uploaded["source_url"],
        timeline=timeline,
        duration_sec=duration_sec,
    )


def render_video_from_source(
    *,
    source_id: str,
    source_url: str | None = None,
    timeline: dict[str, Any],
    duration_sec: float,
) -> dict[str, Any]:
    """Ingest ya subido → wait ready → edit con aspect/fit seguros → URL."""
    from app.services.video_edit_pilot.timeline import aspect_from_dimensions

    if not shotstack_configured():
        raise RuntimeError("SHOTSTACK_API_KEY no configurada")
    width = (timeline.get("source") or {}).get("width")
    height = (timeline.get("source") or {}).get("height")
    url = (source_url or "").strip()
    if not url:
        meta = wait_source_meta(source_id)
        url = meta["source_url"]
        width = meta.get("width") or width
        height = meta.get("height") or height
    try:
        width_i = int(width) if width is not None else None
    except (TypeError, ValueError):
        width_i = None
    try:
        height_i = int(height) if height is not None else None
    except (TypeError, ValueError):
        height_i = None
    aspect = aspect_from_dimensions(width_i, height_i)
    patched = {
        **timeline,
        "output": {
            **(timeline.get("output") or {}),
            "aspect": aspect,
            "fit": "contain",
        },
        "source": {
            **(timeline.get("source") or {}),
            "width": width_i,
            "height": height_i,
        },
        "title": {"enabled": False, "text": "", "mood": None},
    }

    # Sonilo → track de audio (si falla, seguimos sin SFX pero con error visible)
    audio_clips: list[dict[str, Any]] = []
    sonilo_meta: dict[str, Any] = {
        "attempted": False,
        "ok": 0,
        "failed": 0,
        "errors": [],
        "error": None,
        "message": None,
        "mode": None,
    }
    try:
        from app.services.video_edit_pilot.sonilo import (
            resolve_cues_to_audio_clips,
            sonilo_configured,
        )

        cues = list((patched.get("sonilo") or {}).get("cues") or [])
        if not sonilo_configured():
            if cues:
                sonilo_meta["message"] = (
                    f"{len(cues)} cues planificados pero SONILO_API_KEY ausente"
                )
                logger.warning("[VIDEO_EDIT] %s", sonilo_meta["message"])
        else:
            script_bits = [
                str(s.get("text") or "")
                for s in (patched.get("scenes") or [])
                if isinstance(s, dict) and s.get("text")
            ]
            resolved = resolve_cues_to_audio_clips(
                cues,
                max_cues=4,
                video_url=url,
                script_hint=" ".join(script_bits)[:500],
            )
            raw_clips = list(resolved.get("clips") or [])
            # length None (video-to-sfx) → cubrir duración del video
            for clip in raw_clips:
                if not isinstance(clip, dict):
                    continue
                if clip.get("length") is None:
                    clip["length"] = round(max(0.5, float(duration_sec)), 3)
                # Strip helpers no-Shotstack
                clip.pop("sonilo_mode", None)
                clip.pop("task_id", None)
                audio_clips.append(clip)
            sonilo_meta = {
                "attempted": bool(resolved.get("attempted")),
                "ok": int(resolved.get("ok") or 0),
                "failed": int(resolved.get("failed") or 0),
                "errors": list(resolved.get("errors") or [])[:8],
                "error": resolved.get("error"),
                "message": resolved.get("message"),
                "mode": resolved.get("mode"),
            }
            if sonilo_meta["ok"] == 0:
                logger.error(
                    "[VIDEO_EDIT] sonilo 0 clips | mode=%s | %s | errors=%s",
                    sonilo_meta.get("mode"),
                    sonilo_meta.get("message"),
                    sonilo_meta.get("errors"),
                )
            else:
                logger.info(
                    "[VIDEO_EDIT] sonilo sfx ok=%s failed=%s mode=%s cues=%s",
                    sonilo_meta["ok"],
                    sonilo_meta["failed"],
                    sonilo_meta.get("mode"),
                    len(cues),
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[VIDEO_EDIT] sonilo stage skipped: %s", exc)
        sonilo_meta["message"] = f"Sonilo stage exception: {exc}"[:300]
        sonilo_meta["error"] = {
            "ok": False,
            "code": "exception",
            "message": str(exc)[:300],
        }

    edit = timeline_to_shotstack_edit(
        source_url=url,
        timeline=patched,
        duration_sec=duration_sec,
        audio_clips=audio_clips,
    )
    logger.info(
        "[SHOTSTACK] submit edit tracks=%s video_clips=%s audio_clips=%s",
        len((edit.get("timeline") or {}).get("tracks") or []),
        len((((edit.get("timeline") or {}).get("tracks") or [{}])[0].get("clips") or [])),
        len(audio_clips),
    )
    render_id = submit_render(edit)
    result_url = wait_render_done(render_id)
    logger.info(
        "[SHOTSTACK] done render=%s source=%s aspect=%s sonilo=%s url=%s",
        render_id[:12],
        source_id[:12],
        aspect,
        sonilo_meta,
        result_url[:80],
    )
    return {
        "ok": True,
        "render_id": render_id,
        "source_id": source_id,
        "source_url": url,
        "result_url": result_url,
        "edit": edit,
        "aspect": aspect,
        "sonilo": sonilo_meta,
    }
