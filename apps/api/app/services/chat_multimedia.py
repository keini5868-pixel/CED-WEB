"""Dictado Whisper + análisis de imágenes en chat de texto."""

from __future__ import annotations

import base64
import logging
import tempfile
from datetime import date
from typing import Any

import httpx

from app.config import get_settings
from app.deps.auth import is_super_admin
from app.domain.plans import normalize_plan_id
from app.services import supabase_db
from app.services.vision_search import analyze_image

logger = logging.getLogger(__name__)

CHAT_DICTATION_DAILY: dict[str, int] = {
    "free_basic": 0,
    "starter": 30,
    "pro": 100,
    "elite": -1,
    "founding": -1,
    "elite_founding": -1,
    "elite_regular": -1,
}

CHAT_VISION_DAILY: dict[str, int] = {
    "free_basic": 0,
    "starter": 10,
    "pro": 50,
    "elite": 200,
    "founding": 200,
    "elite_founding": 200,
    "elite_regular": 200,
}

MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"},
)


def _effective_plan_key(user_id: str) -> str:
    from app.deps.plan_access import effective_plan_limits
    from app.services.admin_users import get_user_access

    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        return "founding"

    allowed, reason, _ = get_user_access(user_id)
    if allowed and reason == "trial":
        return "elite"

    sub = supabase_db.get_subscription(user_id) or {}
    return normalize_plan_id(sub.get("plan_id"))


def _count_feature_today(user_id: str, event_type: str) -> int:
    try:
        client = supabase_db._client()
        today = date.today().isoformat()
        result = (
            client.table("openai_usage_log")
            .select("id")
            .eq("user_id", user_id)
            .eq("event_type", event_type)
            .gte("created_at", f"{today}T00:00:00")
            .execute()
        )
        return len(result.data or [])
    except Exception:  # noqa: BLE001
        return 0


def _log_feature_usage(
    user_id: str,
    event_type: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        client = supabase_db._client()
        client.table("openai_usage_log").insert(
            {
                "user_id": user_id,
                "event_type": event_type,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CHAT-MM] log usage failed %s", exc)


def _check_daily_limit(
    user_id: str,
    *,
    limits_map: dict[str, int],
    event_type: str,
    feature_label: str,
) -> None:
    from app.services.text_chat import TextChatError

    plan = _effective_plan_key(user_id)
    limit = limits_map.get(plan, 0)
    if limit == 0:
        raise TextChatError(
            f"{feature_label} requiere plan Starter o superior. Mejora en /pricing.",
            http_status=403,
        )
    if limit < 0:
        return
    used = _count_feature_today(user_id, event_type)
    if used >= limit:
        raise TextChatError(
            f"Alcanzaste el límite diario de {feature_label} ({limit}/día). Vuelve mañana o mejora tu plan.",
            http_status=429,
        )


def check_dictation_limit(user_id: str) -> None:
    _check_daily_limit(
        user_id,
        limits_map=CHAT_DICTATION_DAILY,
        event_type="chat_transcribe",
        feature_label="Dictado por voz",
    )


def check_vision_limit(user_id: str) -> None:
    _check_daily_limit(
        user_id,
        limits_map=CHAT_VISION_DAILY,
        event_type="chat_vision",
        feature_label="Análisis de imágenes",
    )


def transcribe_audio(user_id: str, audio_bytes: bytes, *, filename: str = "recording.webm") -> str:
    from app.services.text_chat import TextChatError

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise TextChatError(
            "Audio demasiado largo. Máximo ~1 minuto.",
            http_status=400,
        )
    if not audio_bytes:
        raise TextChatError("Audio vacío.", http_status=400)

    check_dictation_limit(user_id)

    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    if not api_key:
        raise TextChatError(
            "Servicio de dictado temporalmente no disponible.",
            http_status=503,
        )

    suffix = ".webm"
    if filename.lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".webm")):
        suffix = filename[filename.rfind(".") :]

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            with open(tmp.name, "rb") as audio_file:
                with httpx.Client(timeout=60.0) as client:
                    res = client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": (filename, audio_file, "audio/webm")},
                        data={"model": "whisper-1", "language": "es"},
                    )
                    res.raise_for_status()
                    data = res.json()
    except httpx.HTTPStatusError as exc:
        logger.error("[CHAT-MM] whisper %s %s", exc.response.status_code, exc.response.text[:200])
        raise TextChatError(
            "Error transcribiendo audio. Intenta de nuevo.",
            http_status=503,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT-MM] transcribe failed")
        raise TextChatError(
            "Error transcribiendo audio.",
            http_status=500,
        ) from exc

    text = str(data.get("text") or "").strip()
    if not text:
        raise TextChatError("No se detectó voz en la grabación.", http_status=400)

    _log_feature_usage(
        user_id,
        "chat_transcribe",
        metadata={"bytes": len(audio_bytes)},
    )
    return text


def _anthropic_vision_reply(
    *,
    api_key: str,
    image_bytes: bytes,
    media_type: str,
    user_text: str,
) -> str | None:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = user_text.strip() or (
        "Analiza esta imagen como mentor de ventas y marketing digital. "
        "Sé específico, útil y directo en español latino."
    )
    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 900,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            res = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
        blocks = data.get("content") or []
        return "".join(
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CHAT-MM] anthropic vision failed: %s", exc)
        return None


def analyze_chat_image(
    user_id: str,
    *,
    image_bytes: bytes,
    media_type: str,
    user_text: str,
) -> str:
    from app.services.text_chat import TextChatError

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise TextChatError("Imagen demasiado grande. Máximo 5 MB.", http_status=400)
    if media_type not in ALLOWED_IMAGE_TYPES:
        raise TextChatError(
            "Formato no soportado. Usa JPG, PNG, WebP o GIF.",
            http_status=400,
        )

    check_vision_limit(user_id)

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()

    reply: str | None = None
    if anthropic_key:
        reply = _anthropic_vision_reply(
            api_key=anthropic_key,
            image_bytes=image_bytes,
            media_type=media_type,
            user_text=user_text,
        )

    if not reply:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        result = analyze_image(b64, question=user_text)
        if result.get("ok") and result.get("summary"):
            reply = str(result["summary"])
        else:
            err = str(result.get("error") or "No pude analizar la imagen.")
            raise TextChatError(err, http_status=503)

    _log_feature_usage(
        user_id,
        "chat_vision",
        metadata={"bytes": len(image_bytes), "media_type": media_type},
    )
    return reply
