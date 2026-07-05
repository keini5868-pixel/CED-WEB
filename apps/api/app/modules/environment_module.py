"""Módulo ambiente — clima y entorno vía búsqueda web (sin OAuth Weather API)."""

from __future__ import annotations

import logging
import re

from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

ENVIRONMENT_PATTERNS: tuple[str, ...] = (
    r"\b(clima|tiempo|temperatura|calor|fr[ií]o)\b",
    r"\b(va a llover|lluvia|nublado|despejado)\b",
    r"\b(calidad del aire|contaminaci[oó]n|aire)\b",
    r"\b(horas de sol|sol hoy|trabajar afuera)\b",
    r"\b(polen|alergia|al[eé]rgico)\b",
    r"\b(c[oó]mo est[aá] el tiempo|qu[eé] clima)\b",
)

_LOCATION_IN_QUERY = re.compile(
    r"\b(?:clima|tiempo|temperatura|aire|polen)\s+(?:en|de)\s+(.+?)(?:\?|$)",
    re.I,
)

_DEFAULT_PLACE = "Charlotte NC"


def is_environment_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 4:
        return False
    return any(re.search(p, t) for p in ENVIRONMENT_PATTERNS)


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
    return {"spoken": _web_search_environment(user_id, transcript)}


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
        if is_environment_intent(user_text or transcript):
            return await self._run_query(user_id, user_text or transcript)
        return self._idle()

    async def _run_query(self, user_id: str, text: str) -> ModuleResult:
        try:
            spoken = _web_search_environment(user_id, text)
            ok = not spoken.startswith("No pude obtener")
            return ModuleResult(ok=ok, spoken=spoken, handles_response=True)
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
