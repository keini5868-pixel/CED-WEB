"""Módulo mapa / navegación — Capa 3."""

from __future__ import annotations

import asyncio
import logging

from app.modules.base_module import BaseModule
from app.services import voice_client_session as vcs
from app.services.navigation_voice_intent import (
    normalize_navigation_query,
    resolve_navigation_confirm,
    resolve_navigation_place_search,
    resolve_open_map_request,
)
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import NAVIGATION_TIMEOUT_SEC, execute_voice_tool

logger = logging.getLogger(__name__)


def _fresh_map_state() -> dict:
    return {
        "navigation_active": False,
        "pending_destination": None,
        "pending_index": 0,
        "search_results": [],
        "current_step": 0,
        "route": None,
    }


class MapModule(BaseModule):
    name = "map"

    def __init__(self) -> None:
        super().__init__()
        self._state = _fresh_map_state()

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        vcs.set_active_mode(user_id, "map")
        self._active = True
        self._state.update({"navigation_active": False})

        if resolve_open_map_request(user_text) and not resolve_navigation_place_search(
            user_text, utterances or []
        ):
            tool = await execute_voice_tool("activar_modo_conducir", user_id, {})
            spoken = str(tool.get("spoken") or "Abro el mapa, señor.").strip()
            return ModuleResult(
                ok=True,
                spoken=spoken,
                handles_response=True,
                tool_events=[{"type": "module_activated", "module": self.name}],
            )

        nav_req = resolve_navigation_place_search(user_text, utterances or [])
        if nav_req:
            query = normalize_navigation_query(str(nav_req.get("query") or ""))
            if query:
                return await self._search_places(user_id, user_text, query, nav_req)

        return ModuleResult(
            ok=True,
            spoken="Mapa activo, señor. ¿A dónde desea ir?",
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        nav_confirm = resolve_navigation_confirm(
            user_text, utterances or [], user_id=user_id
        )
        if nav_confirm:
            return await self._confirm_navigation(user_id, nav_confirm)

        nav_req = resolve_navigation_place_search(user_text, utterances or [])
        if nav_req:
            query = normalize_navigation_query(str(nav_req.get("query") or ""))
            if query:
                return await self._search_places(user_id, user_text, query, nav_req)

        if resolve_open_map_request(user_text):
            tool = await execute_voice_tool("activar_modo_conducir", user_id, {})
            spoken = str(tool.get("spoken") or "Abro el mapa, señor.").strip()
            return ModuleResult(ok=True, spoken=spoken, handles_response=True)

        return self._idle()

    async def deactivate(self, *, user_id: str, call_id: str) -> None:
        self._state = _fresh_map_state()
        await super().deactivate(user_id=user_id, call_id=call_id)
        from app.services.navigation_session import clear_navigation

        clear_navigation(user_id)
        vcs.set_active_mode(user_id, None)

    async def _search_places(
        self,
        user_id: str,
        user_text: str,
        query: str,
        nav_req: dict,
    ) -> ModuleResult:
        spoken_open = ""
        try:
            if (resolve_open_map_request(user_text) or nav_req.get("open_map")) and (
                vcs.get_active_mode(user_id) != "map"
            ):
                open_result = await execute_voice_tool(
                    "activar_modo_conducir", user_id, {}
                )
                spoken_open = str(open_result.get("spoken") or "").strip()

            tool_result = await asyncio.wait_for(
                execute_voice_tool(
                    "search_nearby_places",
                    user_id,
                    {"query": query, "place": query, "destino": query},
                ),
                timeout=20.0,
            )
            spoken = str(tool_result.get("spoken") or "").strip() or (
                f"No encontré {query} cerca, señor."
            )
            self._state.update(
                {
                    "pending_destination": query,
                    "search_results": tool_result.get("places") or [],
                }
            )
            if spoken_open and not tool_result.get("ok"):
                spoken = spoken_open
        except asyncio.TimeoutError:
            spoken = "Señor, la búsqueda en el mapa tardó demasiado. ¿Repito el lugar?"
        except Exception:
            logger.exception("[MAP_MODULE] search failed user=%s", user_id[:8])
            spoken = "No pude buscar en el mapa, señor."

        return ModuleResult(
            ok=True,
            spoken=spoken,
            handles_response=True,
            tool_events=[{"type": "module_activated", "module": self.name}],
        )

    async def _confirm_navigation(
        self, user_id: str, nav_confirm: dict
    ) -> ModuleResult:
        try:
            action = str(nav_confirm.get("action") or "")
            if action == "begin_navigation":
                tool_result = await asyncio.wait_for(
                    execute_voice_tool("start_navigation", user_id, {}),
                    timeout=NAVIGATION_TIMEOUT_SEC,
                )
            else:
                idx = int(nav_confirm.get("index") or 0)
                tool_result = await asyncio.wait_for(
                    execute_voice_tool(
                        "start_navigation", user_id, {"index": idx}
                    ),
                    timeout=NAVIGATION_TIMEOUT_SEC,
                )
            spoken = str(tool_result.get("spoken") or "Iniciando ruta, señor.").strip()
            self._state.update(
                {
                    "navigation_active": bool(tool_result.get("ok")),
                    "route": tool_result.get("route"),
                    "pending_index": int(nav_confirm.get("index") or 0),
                }
            )
        except asyncio.TimeoutError:
            spoken = "Señor, calcular la ruta tardó demasiado. ¿Repito?"
        except Exception:
            logger.exception("[MAP_MODULE] nav confirm failed")
            spoken = "No pude iniciar la ruta, señor."

        return ModuleResult(ok=True, spoken=spoken, handles_response=True)
