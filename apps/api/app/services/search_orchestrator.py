"""Orquestador búsqueda web → paneles HUD + brief de voz."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.gemini_grounded import fetch_voice_brief
from app.services.panel_bus import publish
from app.services.panel_classifier import classify_panel, panel_payload
from app.services.supabase_db import log_ced_activity
from app.services.tavily_search import tavily_search

logger = logging.getLogger(__name__)

PANEL_SEARCH_DELAY_SEC = 5


def _split_summary_chunks(text: str, size: int = 90) -> list[str]:
    words = text.replace("Señor,", "").strip().split()
    if not words:
        return []
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(" ".join(current)) >= size:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks[:8]


async def run_panel_search(user_id: str, query: str) -> None:
    """Emite eventos HUD — retrasado para no competir con Gemini Live."""
    q = (query or "").strip()
    if not q:
        return

    await asyncio.sleep(PANEL_SEARCH_DELAY_SEC)

    await publish(user_id, {"type": "search_started", "query": q})
    await publish(user_id, {"type": "state", "hud": "searching"})
    await publish(
        user_id,
        {
            "type": "panel_item",
            "panel": "global",
            "payload": panel_payload("Consulta activa", f"Buscando: {q[:100]}"),
        },
    )

    results = await asyncio.to_thread(tavily_search, q)

    for hit in results[:5]:
        title = str(hit.get("title") or "Resultado")
        snippet = str(hit.get("content") or hit.get("snippet") or "")[:220]
        url = str(hit.get("url") or "")
        panel = classify_panel(title, snippet)
        await publish(
            user_id,
            {
                "type": "panel_item",
                "panel": panel,
                "payload": panel_payload(title, snippet, url),
            },
        )
        if panel == "drones":
            await publish(
                user_id,
                {
                    "type": "panel_item",
                    "panel": "global",
                    "payload": panel_payload(title, snippet[:140], url),
                },
            )

    if results:
        fallback = str(results[0].get("content") or results[0].get("title") or "")[:280]
        if fallback:
            for chunk in _split_summary_chunks(fallback):
                await publish(user_id, {"type": "summary_chunk", "text": chunk})

    await publish(user_id, {"type": "state", "hud": "complete"})
    await publish(user_id, {"type": "search_complete"})

    try:
        log_ced_activity(
            user_id,
            "web_search",
            q[:120],
            {"results": len(results), "panels": True},
        )
    except Exception:  # noqa: BLE001
        pass


async def run_voice_search(
    user_id: str,
    query: str,
    *,
    kind: str = "general",
) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "Consulta vacía"}

    await publish(user_id, {"type": "search_started", "query": q})
    await publish(user_id, {"type": "state", "hud": "searching"})
    await publish(
        user_id,
        {
            "type": "panel_item",
            "panel": "global",
            "payload": panel_payload(
                "Consulta activa",
                f"Buscando: {q[:100]}",
            ),
        },
    )

    results = await asyncio.to_thread(tavily_search, q)

    for hit in results[:5]:
        title = str(hit.get("title") or "Resultado")
        snippet = str(hit.get("content") or hit.get("snippet") or "")[:220]
        url = str(hit.get("url") or "")
        panel = classify_panel(title, snippet)
        await publish(
            user_id,
            {
                "type": "panel_item",
                "panel": panel,
                "payload": panel_payload(title, snippet, url),
            },
        )
        if panel == "drones":
            await publish(
                user_id,
                {
                    "type": "panel_item",
                    "panel": "global",
                    "payload": panel_payload(title, snippet[:140], url),
                },
            )

    brief = await asyncio.to_thread(fetch_voice_brief, q, kind=kind)
    summary = str(brief.get("summary") or "").strip() if brief.get("ok") else ""

    if summary:
        for chunk in _split_summary_chunks(summary):
            await publish(user_id, {"type": "summary_chunk", "text": chunk})
            await asyncio.sleep(0.05)
    elif results:
        fallback = str(results[0].get("content") or results[0].get("title") or "")[:280]
        if fallback:
            await publish(user_id, {"type": "summary_chunk", "text": fallback})

    await publish(user_id, {"type": "state", "hud": "complete"})
    await publish(user_id, {"type": "search_complete"})

    try:
        log_ced_activity(
            user_id,
            "web_search",
            q[:120],
            {"results": len(results), "ok": brief.get("ok", False)},
        )
    except Exception:  # noqa: BLE001
        pass

    if brief.get("ok"):
        return {"ok": True, "summary": summary, "kind": kind}
    if summary:
        return {"ok": True, "summary": summary, "kind": kind}
    return {
        "ok": False,
        "error": brief.get("error") or "No se obtuvo información",
    }
