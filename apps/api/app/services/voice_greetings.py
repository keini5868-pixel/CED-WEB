"""Pool de saludos Jarvis v38 — Cartesia TTS con pausas naturales."""

from __future__ import annotations

import logging
import random
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.conversation_memory import user_conversed_within_hours

logger = logging.getLogger(__name__)

DEFAULT_USER_TZ = "America/New_York"


def get_user_timezone(user_id: str | None) -> str:
    """Timezone IANA del perfil; default Charlotte / US East."""
    if not user_id:
        return DEFAULT_USER_TZ
    try:
        from app.services import supabase_db

        profile = supabase_db.get_profile(user_id.strip()) or {}
        tz = str(profile.get("timezone") or "").strip()
        if tz:
            return tz
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_USER_TZ


def get_user_local_hour(user_id: str | None) -> int:
    tz_name = get_user_timezone(user_id)
    try:
        return datetime.now(ZoneInfo(tz_name)).hour
    except Exception:  # noqa: BLE001
        return datetime.now().hour


CONTINUITY_GREETING = (
    "De regreso, señor. ¿Continuamos donde dejamos… o iniciamos misión nueva?"
)

# 8 saludos aprobados — puntuación optimizada para pausas Cartesia
JARVIS_GREETING_POOL: tuple[str, ...] = (
    "Hola, señor. Activando protocolos… para lo que necesite. "
    "CED completamente operativo, y a su disposición.",
    "Buenos días, señor. CED en línea. Sistema completo a su disposición — "
    "voz, visión, redes, prospección, análisis y más. ¿Por dónde comenzamos hoy?",
    "A sus órdenes, señor. Todos los sistemas operativos, y listos. "
    "Estoy aquí para ayudarle a generar, ejecutar y conquistar. ¿Qué necesita?",
    "Sistema CED en línea, señor. Inteligencia central activada. "
    "Listo para asistirle — desde análisis, hasta ejecución completa.",
    "A su servicio, señor. CED completamente operativo — voz Jarvis, visión inteligente, "
    "redes, conocimiento interno, y conexión con el mundo. Cuénteme qué construimos hoy.",
    "Bienvenido, señor. CED activado, y listo para acción. "
    "Cámara, redes, búsquedas, publicaciones — todo a su servicio. Indíqueme.",
    "Hola, señor. Activando todas mis capacidades para usted. "
    "Voz, visión, prospección, conocimiento — listos para lo que decida. Cuente conmigo.",
    "Señor… CED reportándose al comando central. Sistemas verificados, al cien por ciento. "
    "Dígame qué misión emprendemos hoy.",
)

_TIME_PREFIXES = (
    (5, 12, ("Buenos días, señor.", "Buenos días, señor.")),
    (12, 19, ("Buenas tardes, señor.", "Buenas tardes, señor.")),
    (19, 24, ("Buenas noches, señor.", "Buenas noches, señor.")),
    (0, 5, ("Buenas noches, señor.", "Buenas noches, señor.")),
)

_last_greeting_index: dict[str, int] = {}


def _hour_prefix(hour: int) -> str | None:
    for start, end, prefixes in _TIME_PREFIXES:
        if start <= hour < end:
            return prefixes[0]
    return None


def _adapt_time_of_day(text: str, *, tz_name: str = DEFAULT_USER_TZ) -> str:
    try:
        hour = datetime.now(ZoneInfo(tz_name)).hour
    except Exception:  # noqa: BLE001
        hour = datetime.now().hour
    prefix = _hour_prefix(hour)
    if not prefix:
        return text
    lowered = text.lower()
    if any(
        lowered.startswith(p.lower())
        for p in ("hola, señor", "buenos días", "buenas tardes", "buenas noches", "bienvenido")
    ):
        if lowered.startswith("hola, señor"):
            return prefix + text[len("Hola, señor") :]
        if lowered.startswith("bienvenido, señor"):
            return prefix + text[len("Bienvenido, señor") :]
    return text


def _pick_pool_index(user_id: str | None) -> int:
    pool_size = len(JARVIS_GREETING_POOL)
    if pool_size <= 1:
        return 0
    uid = (user_id or "").strip() or "_anon"
    last = _last_greeting_index.get(uid)
    choices = [i for i in range(pool_size) if i != last]
    idx = random.choice(choices)
    _last_greeting_index[uid] = idx
    return idx


def pick_jarvis_greeting(user_id: str | None = None) -> str:
    """Elige saludo del pool v38 con continuidad, hora del día y sin repetir el último."""
    if user_id and user_conversed_within_hours(user_id, hours=4.0):
        logger.info("[GREETING] pool=continuity user=%s", user_id[:8])
        return CONTINUITY_GREETING

    idx = _pick_pool_index(user_id)
    greeting = JARVIS_GREETING_POOL[idx]
    tz_name = get_user_timezone(user_id)
    greeting = _adapt_time_of_day(greeting, tz_name=tz_name)
    logger.info(
        "[GREETING] pool=%s user=%s tz=%s hour=%s",
        idx + 1,
        (user_id or "?")[:8],
        tz_name,
        get_user_local_hour(user_id),
    )
    return greeting
