"""Módulo ambiente — clima y entorno vía búsqueda web (sin OAuth Weather API)."""

from __future__ import annotations

import logging
import re

from app.modules.base_module import BaseModule
from app.modules.module_acks import MODULE_ACKS
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

ENVIRONMENT_PATTERNS: tuple[str, ...] = (
    r"\b(clima|tiempo|temperatura|calor|fr[ií]o)\b",
    r"\b(va a llover|lluvia|nublado|despejado)\b",
    r"\b(calidad\s+(?:del?\s+)?aire|contaminaci[oó]n)\b",
    r"\b(horas de sol|sol hoy|trabajar afuera)\b",
    r"\b(polen|alergia|al[eé]rgico)\b",
    r"\b(c[oó]mo est[aá] el tiempo|qu[eé] clima)\b",
)

_LOCATION_IN_QUERY = re.compile(
    r"\b(?:clima|tiempo|temperatura|aire|polen|calidad(?:\s+(?:del?\s+)?aire)?)\s+(?:en|de)\s+(.+?)(?:\?|$)",
    re.I,
)

_QUESTION_WORDS = re.compile(
    r"\b(qu[ée]|c[óo]mo|cu[áa]ndo|d[óo]nde|por\s?qu[ée]|para\s?qu[ée])\b",
    re.I,
)

_DEFAULT_PLACE = "Charlotte NC"


def is_environment_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 4:
        return False
    return any(re.search(p, t) for p in ENVIRONMENT_PATTERNS)


def is_environment_topic(text: str) -> bool:
    """True si el turno trata clima/calidad del aire/polen (ancla estricta o patterns)."""
    if is_environment_intent(text):
        return True
    from app.services.ced_orchestrator import detect_strict_intent_v2

    return detect_strict_intent_v2(text) == "environment"


def _utterance_text(item: object) -> tuple[str, str]:
    if isinstance(item, dict):
        return str(item.get("role") or ""), str(item.get("content") or "").strip()
    role = getattr(item, "role", "") or ""
    content = getattr(item, "content", "") or ""
    return str(role), str(content).strip()


def recent_environment_user_query(
    transcript: list,
    *,
    exclude: str = "",
) -> str | None:
    """Última pregunta del usuario sobre ambiente antes del turno actual."""
    exclude_norm = (exclude or "").strip().lower()
    user_lines = list(_iter_transcript_user_lines(transcript))
    for text in reversed(user_lines):
        if not text:
            continue
        if exclude_norm and text.strip().lower() == exclude_norm:
            continue
        if is_environment_topic(text):
            return text
    return None


def _iter_transcript_user_lines(transcript: list):
    for item in transcript or []:
        role, text = _utterance_text(item)
        if role.lower() != "user":
            continue
        yield text


def is_environment_location_followup(text: str) -> bool:
    """Respuesta corta de ubicación tras una consulta ambiental (ej. «Charlotte»)."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if is_environment_topic(t):
        return False
    if _QUESTION_WORDS.search(t) and len(t.split()) > 4:
        return False
    words = [w for w in re.split(r"\s+", t) if w]
    if not 1 <= len(words) <= 8:
        return False
    if any(ch.isdigit() for ch in t):
        return False
    return True


def compose_environment_query(user_text: str, transcript: list | None = None) -> str:
    """Combina consulta ambiental previa + ubicación en un solo texto para búsqueda."""
    current = (user_text or "").strip()
    if not is_environment_location_followup(current):
        return current
    prior = recent_environment_user_query(transcript or [], exclude=current)
    if not prior:
        return current
    place = current.rstrip("?.,").strip()
    if re.search(r"\b(?:en|de)\s+", place, re.I):
        return f"{prior} {place}"
    return f"{prior} en {place}"


def _extract_place_from_query(text: str) -> str:
    match = _LOCATION_IN_QUERY.search(text or "")
    if match:
        return match.group(1).strip(" ?.:,")
    return ""


def resolve_environment_place(user_id: str, transcript: str = "") -> str:
    """Lugar para la búsqueda: texto en pregunta → Charlotte NC."""
    place = _extract_place_from_query(transcript)
    if place:
        return place
    t = (transcript or "").strip()
    if is_environment_location_followup(t) and not is_environment_topic(t):
        return t.rstrip("?.,").strip()
    return _DEFAULT_PLACE


def build_environment_search_query(user_id: str, transcript: str) -> str:
    place = resolve_environment_place(user_id, transcript)
    t = (transcript or "").lower()
    if any(w in t for w in ["polen", "alergia", "alérgico", "alergico"]):
        return f"polen {place} hoy"
    if any(w in t for w in ["aire", "contaminación", "contaminacion", "calidad"]):
        return f"calidad del aire {place} hoy"
    if any(w in t for w in ["sol", "solar"]):
        return f"horas de sol {place} hoy"
    return f"clima {place} hoy"


def _web_search_environment(user_id: str, transcript: str) -> str:
    from app.services.gemini_grounded import execute_search_web_sync

    query = build_environment_search_query(user_id, transcript)
    result = execute_search_web_sync(query, kind="weather")
    summary = str(result.get("summary") or result.get("message") or "").strip()
    if result.get("ok") and summary:
        spoken = summary if summary.lower().startswith("señor") else f"Señor, {summary.rstrip('.')}."
        if any(w in (transcript or "").lower() for w in ["afuera", "exterior", "trabajar"]):
            spoken = spoken.rstrip(".") + ". Excelente referencia para planificar actividades al exterior."
        return spoken
    return (
        "No pude obtener datos ambientales en este momento, señor. "
        "Intente de nuevo en unos minutos."
    )


def handle_environment_query_sync(user_id: str, transcript: str) -> dict[str, str]:
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_web_search_environment, user_id, transcript)
        try:
            spoken = future.result(timeout=22)
        except concurrent.futures.TimeoutError:
            spoken = (
                "Señor, la consulta del clima está tardando. "
                "Intente de nuevo en unos segundos o use el botón CLIMA en la barra."
            )
        except Exception:  # noqa: BLE001
            logger.exception("[ENV] sync query failed user=%s", user_id[:8])
            spoken = (
                "No pude obtener datos ambientales en este momento, señor. "
                "Intente de nuevo en unos minutos."
            )
    return {"spoken": spoken}


class EnvironmentModule(BaseModule):
    name = "environment"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._active = True
        return await self._run_query(user_id, user_text or transcript)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        query = compose_environment_query(
            user_text or transcript,
            utterances or [],
        )
        if is_environment_topic(query) or is_environment_location_followup(user_text or transcript):
            return await self._run_query(user_id, query)
        return self._idle()

    async def _run_query(self, user_id: str, text: str) -> ModuleResult:
        try:
            spoken = _web_search_environment(user_id, text)
            ok = not spoken.startswith("No pude obtener")
            return ModuleResult(
                ok=ok,
                spoken=spoken,
                handles_response=True,
                send_filler=True,
                filler=MODULE_ACKS.get("environment", "Consultando el ambiente, señor."),
            )
        except Exception:  # noqa: BLE001
            logger.exception("[ENV] module query failed user=%s", user_id[:8])
            return ModuleResult(
                ok=False,
                spoken=(
                    "No pude obtener datos ambientales en este momento, señor. "
                    "Intente de nuevo en unos minutos."
                ),
                handles_response=True,
            )
