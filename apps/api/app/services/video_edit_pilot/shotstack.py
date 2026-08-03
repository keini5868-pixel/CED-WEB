"""Cliente Shotstack Edit + Ingest (stage/v1)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_UPLOAD_TIMEOUT = 180.0
_POLL_INTERVAL = 2.5
_INGEST_MAX_WAIT = 120.0
_RENDER_MAX_WAIT = 180.0


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
                return src
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
) -> dict[str, Any]:
    """Convierte timeline CED → JSON Edit API (cortes + fades)."""
    scenes = list(timeline.get("scenes") or [])
    transitions = {
        float(t.get("at") or 0): t
        for t in (timeline.get("transitions") or [])
        if isinstance(t, dict)
    }
    clips: list[dict[str, Any]] = []
    cursor = 0.0
    if not scenes:
        clips.append(
            {
                "asset": {"type": "video", "src": source_url, "trim": 0},
                "start": 0,
                "length": max(0.5, float(duration_sec)),
            }
        )
    else:
        for i, scene in enumerate(scenes):
            start_src = float(scene.get("start") or 0)
            end_src = float(scene.get("end") or start_src)
            length = max(0.2, end_src - start_src)
            clip: dict[str, Any] = {
                "asset": {
                    "type": "video",
                    "src": source_url,
                    "trim": round(start_src, 3),
                },
                "start": round(cursor, 3),
                "length": round(length, 3),
            }
            # Transición out si hay fade/veo en el borde
            edge = transitions.get(round(end_src, 2)) or transitions.get(end_src)
            if edge and i < len(scenes) - 1:
                ttype = str(edge.get("type") or "fade")
                if ttype != "veo_lite":
                    clip["transition"] = {"out": "fade"}
                else:
                    # Veo aún no genera clip; usamos fade como fallback seguro
                    clip["transition"] = {"out": "fade"}
            clips.append(clip)
            cursor += length

    output = timeline.get("output") or {}
    aspect = str(output.get("aspect") or "9:16")
    return {
        "timeline": {
            "background": "#000000",
            "tracks": [{"clips": clips}],
        },
        "output": {
            "format": "mp4",
            "resolution": "hd",
            "aspectRatio": aspect if aspect in {"16:9", "9:16", "1:1", "4:5"} else "9:16",
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
    """Ingest ya subido (browser/API) → wait ready si hace falta → edit → URL."""
    if not shotstack_configured():
        raise RuntimeError("SHOTSTACK_API_KEY no configurada")
    url = (source_url or "").strip()
    if not url:
        url = wait_source_ready(source_id)
    edit = timeline_to_shotstack_edit(
        source_url=url,
        timeline=timeline,
        duration_sec=duration_sec,
    )
    render_id = submit_render(edit)
    result_url = wait_render_done(render_id)
    logger.info(
        "[SHOTSTACK] done render=%s source=%s url=%s",
        render_id[:12],
        source_id[:12],
        result_url[:80],
    )
    return {
        "ok": True,
        "render_id": render_id,
        "source_id": source_id,
        "source_url": url,
        "result_url": result_url,
        "edit": edit,
    }
