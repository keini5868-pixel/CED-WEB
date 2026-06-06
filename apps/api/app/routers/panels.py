"""Paneles HUD — SSE stream + búsqueda en background."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.panel_bus import stream_events
from app.services.search_orchestrator import run_panel_search, run_voice_search

router = APIRouter(prefix="/v1/panels", tags=["panels"])


class PanelSearchBody(BaseModel):
    query: str = Field(default="", max_length=500)
    kind: str = Field(default="general")


@router.get("/stream")
async def panel_stream(user_id: str = Depends(require_user_id)) -> StreamingResponse:
    """SSE — eventos de paneles GLOBAL / DRONES / SUMMARY / WAVES."""

    async def generator():
        async for payload in stream_events(user_id):
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/search")
async def panel_search_background(
    body: PanelSearchBody,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Llena paneles HUD sin bloquear la ruta de voz."""
    q = body.query.strip()
    if not q:
        return {"ok": False, "error": "Consulta vacía"}
    background_tasks.add_task(run_panel_search, user_id, q)
    return {"ok": True, "started": True}


@router.post("/voice-search")
async def voice_search(
    body: PanelSearchBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Legacy — paneles + brief en una sola llamada (preferir /search + voice-brief)."""
    kind = body.kind if body.kind in ("news", "general") else "general"
    return await run_voice_search(user_id, body.query, kind=kind)
