"""Orquestador CED — Capa 2: detecta módulos, estados aislados, un módulo activo."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.modules.environment_module import is_environment_intent
from app.modules.calendar_module import is_calendar_intent
from app.modules.gmail_module import is_gmail_intent
from app.modules.base_module import BaseModule
from app.modules.module_registry import MODULE_ACKS, MODULE_ORDER, MODULE_OVERLAYS, build_module
from app.services import voice_client_session as vcs
from app.services.cognitive_intents import (
    is_brand_followup_question,
    is_camera_activation_intent,
    is_camera_deactivation_intent,
    is_meta_publish_intent,
    is_topic_change,
)
from app.services.navigation_voice_intent import (
    resolve_navigation_confirm,
    resolve_navigation_place_search,
    resolve_open_map_request,
)
from app.services.orchestrator_types import ModuleResult, OrchestratorResult
from app.services.retell_custom_llm import (
    resolve_camera_voice_request,
    resolve_meta_publish_request,
    resolve_social_comments_request,
    resolve_web_search_request,
    _is_pure_ack,
)
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

_IMAGE_GEN_PATTERNS = (
    r"\b(?:genera(?:r|me)?|crea(?:r|me)?|cr[eé]ame|gener[aá]me|haz(?:me)?|dise[nñ]a(?:r|me)?|dibuja(?:r|me)?|pinta(?:r|me)?)\s+(?:una?\s+)?(?:imagen|foto|picture|ilustraci[oó]n|dise[nñ]o|arte|logo|banner|flyer|portada)\b",
    r"\b(?:imagen|foto)\s+(?:de|con|para)\b",
    r"\b(?:necesito|quiero)\s+(?:una?\s+)?(?:imagen|foto|dise[nñ]o)\b",
)
_PDF_PATTERNS = (
    r"\b(?:genera|generar|crea|crear|haz|exporta)\s+(?:un\s+)?pdf\b",
    r"\bpdf\s+(?:de|con|sobre)\b",
)
_PROSPECTION_PATTERNS = (
    r"\b(?:prospecci[oó]n|prospectar|prospectos?)\b",
    r"\b(?:activa|desactiva|reporte)\s+(?:la\s+)?prospecci[oó]n\b",
)
_MEMORY_PATTERNS = (
    r"\b(?:recuerda|guarda|anota|memoriza)\b",
    r"\b(?:no\s+olvides|no\s+te\s+olvides)\b",
)

DETECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "calendar": (
        r"\b(?:qu[eé]|que)\s+tengo\s+ma[nñ]ana\b",
        r"\b(?:ag[eé]ndame|agendar|programa(?:r|me))\s+(?:una\s+)?cita\b",
        r"\b(?:qu[eé]|que)\s+eventos\s+tengo\b",
        r"\b(?:mi\s+)?calendario\b",
    ),
    "gmail": (
        r"\b(?:emails?|correos?|gmail)\b.*\bimportant",
        r"\bl[eé]eme\s+(?:el\s+)?(?:email|correo)\b",
        r"\benv[ií]a\s+(?:un\s+)?(?:email|correo)\b",
    ),
    "environment": (
        r"\b(clima|tiempo|temperatura|calor|fr[ií]o)\b",
        r"\b(va a llover|lluvia|nublado|despejado)\b",
        r"\b(calidad del aire|contaminaci[oó]n|aire)\b",
        r"\b(horas de sol|sol hoy|trabajar afuera)\b",
        r"\b(polen|alergia|al[eé]rgico)\b",
        r"\b(c[oó]mo est[aá] el tiempo|qu[eé] clima)\b",
    ),
    "web_search": (
        r"\b(noticias|últimas noticias|qué pasó)\b",
        r"\b(clima en|temperatura en)\b",
        r"\b(precio de|cuánto cuesta)\b",
        r"\b(busca información|busca en internet)\b",
        r"\b(quién es|qué es|cómo funciona)\b.*\b(hoy|ahora|actual)\b",
        r"\b(declaraciones de|dijo|anunció)\b",
    ),
    "publish": (
        r"\b(publica|publicar|postea|postear)\b",
        r"\b(sube a instagram|sube a facebook)\b",
        r"\b(comparte en|publica esto|publica eso)\b",
    ),
    "map": (
        r"\b(abre el mapa|activa el mapa|modo conducir)\b",
        r"\b(llévame a|navega a|cómo llego a)\b",
        r"\b(busca cerca|dónde hay|encuentra un)\b",
    ),
    "camera": (
        r"\b(activa la cámara|enciende la cámara)\b",
        r"\b(qué ves|qué me muestro|analiza esto)\b",
        r"\b(describe lo que|qué es esto)\b",
    ),
    "image_gen": (
        r"\b(genera(?:r|me)?|crea(?:r|me)?|cr[eé]ame|gener[aá]me|haz(?:me)?|dise[nñ]a(?:r|me)?)\s+(?:una?\s+)?(?:imagen|foto|dise[nñ]o)\b",
        r"\b(dibuja(?:r|me)?|pinta(?:r|me)?)\s+(?:una?\s+)?(?:imagen|foto|dise[nñ]o)\b",
        r"\b(genera un diseño|crea un diseño|hazme una imagen)\b",
    ),
    "pdf": (
        r"\b(genera un pdf|crea un pdf|hazme un pdf)\b",
        r"\b(genera el documento|crea el reporte)\b",
    ),
    "prospection": (
        r"\b(modo prospección|activa prospección)\b",
        r"\b(buscar prospectos|modo ventas)\b",
        r"\b(activar castillo|modo ascenso)\b",
    ),
    "memory": (
        r"\b(recuerda que|guarda esto|registra)\b",
        r"\b(agrega al crm|nuevo cliente|añade contacto)\b",
    ),
    "finance": (
        r"\b(gast[ée]|pagu[ée]|compr[ée])\b.*\d",
        r"\b(recib[íi]|gan[ée]|me pagaron|cobr[ée])\b.*\d",
        r"\bc[óo]mo\s+voy\b.*\b(mes|finanzas|dinero)\b",
        r"\bmis\s+finanzas\b",
        r"\bplan\s+de\s+ahorro\b",
        r"\bcu[áa]nto\s+(?:he\s+)?gast[ée]\b",
    ),
}

_orchestrators: dict[str, "CedOrchestrator"] = {}

_EPHEMERAL_MODULES = frozenset(
    {"calendar", "gmail", "environment", "web_search", "image_gen", "pdf", "publish", "finance"}
)


def is_module_command(
    user_text: str,
    module: str,
    transcript: list[Utterance],
    *,
    user_id: str = "",
) -> bool:
    text = (user_text or "").strip()
    if not text or not module:
        return False
    if module == "camera":
        return bool(
            is_camera_activation_intent(text)
            or is_camera_deactivation_intent(text)
            or is_brand_followup_question(text)
            or resolve_camera_voice_request(text)
        )
    if module == "map":
        return bool(
            resolve_navigation_confirm(text, transcript, user_id=user_id)
            or resolve_navigation_place_search(text, transcript)
            or resolve_open_map_request(text)
        )
    if module == "publish":
        return bool(
            is_meta_publish_intent(text)
            or resolve_meta_publish_request(text, transcript)
            or resolve_social_comments_request(text)
        )
    if module == "web_search":
        return resolve_web_search_request(text, transcript) is not None
    if module == "calendar":
        return is_calendar_intent(text)
    if module == "gmail":
        return is_gmail_intent(text)
    if module == "environment":
        return is_environment_intent(text)
    if module in ("image_gen", "pdf", "prospection", "memory"):
        detected = detect_module(text, transcript, user_id=user_id, active_module=module)
        return detected == module
    return False


def detect_module_from_patterns(text: str) -> str | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    for module in MODULE_ORDER:
        for pattern in DETECTION_PATTERNS.get(module, ()):
            if re.search(pattern, t):
                return module
    return None


def detect_module(
    user_text: str,
    transcript: list[Utterance],
    *,
    user_id: str = "",
    active_module: str | None = None,
) -> str | None:
    """Detecta qué módulo debe manejar el turno. Un solo módulo a la vez."""
    text = (user_text or "").strip()
    if not text:
        return None

    t = text.lower()
    if active_module and _is_pure_ack(text):
        return active_module

    if is_meta_publish_intent(text) or resolve_meta_publish_request(text, transcript):
        return "publish"
    if resolve_social_comments_request(text):
        return "publish"

    if any(re.search(p, t) for p in _IMAGE_GEN_PATTERNS):
        return "image_gen"
    if any(re.search(p, t) for p in _PDF_PATTERNS):
        return "pdf"
    if any(re.search(p, t) for p in _PROSPECTION_PATTERNS):
        return "prospection"
    if any(re.search(p, t) for p in _MEMORY_PATTERNS):
        return "memory"

    if active_module == "map":
        if (
            resolve_navigation_confirm(text, transcript, user_id=user_id)
            or resolve_navigation_place_search(text, transcript)
            or resolve_open_map_request(text)
        ):
            return "map"

    if active_module == "publish":
        if resolve_meta_publish_request(text, transcript):
            return "publish"

    if active_module == "camera":
        if (
            is_camera_activation_intent(text)
            or is_camera_deactivation_intent(text)
            or is_brand_followup_question(text)
            or resolve_camera_voice_request(text)
        ):
            return "camera"

    if active_module in (
        "calendar",
        "gmail",
        "environment",
        "web_search",
        "image_gen",
        "pdf",
        "prospection",
        "memory",
    ):
        detected = _detect_fresh_module(text, transcript, user_id=user_id)
        if detected == active_module:
            return active_module
        if detected and detected != active_module:
            return detected
        return active_module

    if is_calendar_intent(text):
        return "calendar"

    if is_gmail_intent(text):
        return "gmail"

    if resolve_navigation_confirm(text, transcript, user_id=user_id):
        return "map"
    nav_place = resolve_navigation_place_search(text, transcript)
    if nav_place or resolve_open_map_request(text):
        return "map"

    if is_camera_activation_intent(text) or resolve_camera_voice_request(text):
        return "camera"

    if resolve_meta_publish_request(text, transcript):
        return "publish"

    if resolve_social_comments_request(text):
        return "publish"

    if is_environment_intent(text):
        return "environment"

    if resolve_web_search_request(text, transcript):
        return "web_search"

    patterned = detect_module_from_patterns(text)
    if patterned:
        return patterned

    return _detect_fresh_module(text, transcript, user_id=user_id)


def _detect_fresh_module(
    user_text: str,
    transcript: list[Utterance],
    *,
    user_id: str = "",
) -> str | None:
    t = user_text.lower()
    if any(re.search(p, t) for p in _IMAGE_GEN_PATTERNS):
        return "image_gen"
    if any(re.search(p, t) for p in _PDF_PATTERNS):
        return "pdf"
    if any(re.search(p, t) for p in _PROSPECTION_PATTERNS):
        return "prospection"
    if any(re.search(p, t) for p in _MEMORY_PATTERNS):
        return "memory"
    if is_meta_publish_intent(user_text):
        return "publish"
    return None


def get_context_overlay(module_name: str | None) -> str | None:
    if not module_name:
        return None
    return MODULE_OVERLAYS.get(module_name)


class CedOrchestrator:
    """Estado aislado por módulo; corre en paralelo con Gemini."""

    def __init__(self, *, call_id: str) -> None:
        self.call_id = call_id
        self.active_module: str | None = None
        self._modules: dict[str, BaseModule] = {}
        self._module_states: dict[str, dict[str, Any]] = {}

    def _get_module(self, name: str) -> BaseModule:
        if name not in self._modules:
            self._modules[name] = build_module(name)
            self._module_states.setdefault(name, {})
        return self._modules[name]

    async def deactivate_current(self, *, user_id: str) -> None:
        if not self.active_module:
            return
        prev = self.active_module
        try:
            await self._get_module(prev).deactivate(
                user_id=user_id, call_id=self.call_id
            )
        except Exception:
            logger.exception("[ORCH] deactivate failed module=%s", prev)
        self._module_states[prev] = self._get_module(prev).get_state()
        self.active_module = None
        vcs.push_tool_event(user_id, {"type": "module_deactivated", "module": prev})

    async def activate_module(
        self,
        name: str,
        *,
        user_text: str,
        transcript: list[Utterance],
        user_id: str,
    ) -> ModuleResult:
        if self.active_module and self.active_module != name:
            await self.deactivate_current(user_id=user_id)

        self.active_module = name
        vcs.set_active_mode(user_id, name)
        module = self._get_module(name)
        result = await module.activate(
            user_text,
            user_id=user_id,
            call_id=self.call_id,
            user_text=user_text,
            utterances=transcript,
        )
        self._module_states[name] = module.get_state()
        self._emit_module_events(user_id, name, result)
        return result

    async def handle_active(
        self,
        *,
        user_text: str,
        transcript: list[Utterance],
        user_id: str,
    ) -> ModuleResult | None:
        if not self.active_module:
            return None
        module = self._get_module(self.active_module)
        result = await module.handle_command(
            user_text,
            user_id=user_id,
            call_id=self.call_id,
            user_text=user_text,
            utterances=transcript,
        )
        self._module_states[self.active_module] = module.get_state()
        if result.handles_response or result.tool_events:
            self._emit_module_events(user_id, self.active_module, result)
        return result

    async def _release_ephemeral_module(self, user_id: str) -> None:
        if self.active_module in _EPHEMERAL_MODULES:
            await self.deactivate_current(user_id=user_id)

    async def process(
        self,
        *,
        user_text: str,
        transcript: list[Utterance],
        call_id: str,
        user_id: str,
    ) -> OrchestratorResult:
        if (
            self.active_module
            and is_topic_change(user_text)
            and not is_module_command(
                user_text,
                self.active_module,
                transcript,
                user_id=user_id,
            )
        ):
            await self.deactivate_current(user_id=user_id)

        overlay = get_context_overlay(self.active_module)

        if self.active_module:
            active_result = await self.handle_active(
                user_text=user_text,
                transcript=transcript,
                user_id=user_id,
            )
            if active_result and active_result.handles_response:
                result = self._to_orch_result(
                    active_result,
                    module_activated=None,
                    overlay=get_context_overlay(self.active_module),
                )
                if is_camera_deactivation_intent(user_text):
                    await self.deactivate_current(user_id=user_id)
                else:
                    await self._release_ephemeral_module(user_id)
                return result

        detected = detect_module(
            user_text,
            transcript,
            user_id=user_id,
            active_module=self.active_module,
        )

        if detected:
            if detected != self.active_module:
                result = await self.activate_module(
                    detected,
                    user_text=user_text,
                    transcript=transcript,
                    user_id=user_id,
                )
                activated = detected
            else:
                result = await self._get_module(detected).handle_command(
                    user_text,
                    user_id=user_id,
                    call_id=self.call_id,
                    user_text=user_text,
                    utterances=transcript,
                )
                activated = None

            if result.handles_response:
                orch_result = self._to_orch_result(
                    result,
                    module_activated=activated,
                    overlay=get_context_overlay(detected),
                )
                await self._release_ephemeral_module(user_id)
                return orch_result
            if activated:
                return OrchestratorResult(
                    module_activated=activated,
                    context_overlay=get_context_overlay(detected),
                    conversation_continues=True,
                )

        comments = resolve_social_comments_request(user_text)
        if comments and user_id:
            result = await self._handle_comments(user_id, comments)
            if result.handles_response:
                return self._to_orch_result(result, overlay=overlay)

        return OrchestratorResult.conversation_only(overlay=get_context_overlay(self.active_module))

    async def _handle_comments(
        self, user_id: str, comments: dict[str, str]
    ) -> ModuleResult:
        from app.services.voice_tool_executor import execute_voice_tool
        import asyncio

        try:
            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "leer_comentarios_redes",
                    user_id,
                    {"platform": comments["platform"]},
                ),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            return ModuleResult(
                ok=False,
                spoken="No pude leer los comentarios a tiempo, señor.",
                handles_response=True,
            )
        spoken = str(tool_result.get("spoken") or "").strip() or (
            "No pude consultar los comentarios, señor."
        )
        return ModuleResult(ok=True, spoken=spoken, handles_response=True)

    def _emit_module_events(
        self, user_id: str, module_name: str, result: ModuleResult
    ) -> None:
        vcs.push_tool_event(
            user_id, {"type": "module_activated", "module": module_name}
        )
        for ev in result.tool_events:
            if ev.get("type") != "module_activated":
                vcs.push_tool_event(user_id, ev)

    @staticmethod
    def _to_orch_result(
        result: ModuleResult,
        *,
        module_activated: str | None = None,
        overlay: str | None = None,
    ) -> OrchestratorResult:
        filler = result.filler or (
            MODULE_ACKS.get(module_activated or "", "") if result.send_filler else ""
        )
        return OrchestratorResult(
            module_activated=module_activated,
            module_result=result,
            context_overlay=overlay,
            conversation_continues=result.conversation_continues,
            handles_response=result.handles_response,
            spoken=result.spoken,
            filler=filler,
            send_filler=result.send_filler,
        )


def get_orchestrator(call_id: str) -> CedOrchestrator:
    cid = (call_id or "").strip()
    if cid not in _orchestrators:
        _orchestrators[cid] = CedOrchestrator(call_id=cid)
    return _orchestrators[cid]


class CedOrchestratorFacade:
    """Singleton de acceso al orquestador por call_id."""

    DETECTION_PATTERNS = DETECTION_PATTERNS
    CONTEXT_OVERLAYS = MODULE_OVERLAYS

    def get(self, call_id: str) -> CedOrchestrator:
        return get_orchestrator(call_id)

    async def process(
        self,
        *,
        user_text: str,
        transcript: list[Utterance],
        call_id: str,
        user_id: str,
    ) -> OrchestratorResult:
        return await self.get(call_id).process(
            user_text=user_text,
            transcript=transcript,
            call_id=call_id,
            user_id=user_id,
        )

    def get_context_overlay(self, call_id: str) -> str | None:
        orch = self.get(call_id)
        return get_context_overlay(orch.active_module)


ced_orchestrator = CedOrchestratorFacade()
