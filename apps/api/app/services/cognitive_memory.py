"""Memoria cognitiva — Postgres por usuario (SaaS)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.services import supabase_db

logger = logging.getLogger(__name__)

MAX_CONTENT = 4000
MAX_KEY = 120


def _client():
    return supabase_db._client()


def save_memory(
    user_id: str,
    key: str,
    content: str,
    *,
    category: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    mem_key = (key or "").strip()[:MAX_KEY]
    body = (content or "").strip()[:MAX_CONTENT]
    if not mem_key or not body:
        raise ValueError("Clave y contenido son obligatorios")

    try:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "user_id": user_id,
            "mem_key": mem_key,
            "content": body,
            "category": (category or "general")[:40],
            "tags": tags or [],
            "updated_at": now,
        }
        result = _client().table("cognitive_memories").upsert(
            row, on_conflict="user_id,mem_key"
        ).execute()
        supabase_db.log_ced_activity(
            user_id, "memory_save", detail=mem_key[:80], meta={"category": row["category"]}
        )
        saved = (result.data or [row])[0]
        logger.info("[MEMORY] save user=%s key=%s", user_id[:8], mem_key)
        return {"ok": True, "key": mem_key, "id": saved.get("id")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[MEMORY] save failed %s", exc)
        return {
            "ok": False,
            "error": "Ejecute la migración 005_cognitive_memory.sql en Supabase",
        }


def get_memory(user_id: str, key: str) -> dict[str, Any]:
    mem_key = (key or "").strip()
    if not mem_key:
        raise ValueError("Clave requerida")
    result = (
        _client()
        .table("cognitive_memories")
        .select("mem_key, content, category, tags, updated_at")
        .eq("user_id", user_id)
        .eq("mem_key", mem_key)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return {"ok": False, "error": "No encontré esa memoria"}
    row = rows[0]
    return {
        "ok": True,
        "key": row["mem_key"],
        "content": row["content"],
        "category": row.get("category"),
        "tags": row.get("tags") or [],
    }


def search_memory(user_id: str, query: str, *, limit: int = 5) -> dict[str, Any]:
    q = (query or "").strip()
    try:
        client = _client()
        if not q:
            result = (
                client.table("cognitive_memories")
                .select("mem_key, content, category, updated_at")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )
            hits = result.data or []
        else:
            safe_q = re.sub(r"[%_]", "", q)
            result = (
                client.table("cognitive_memories")
                .select("mem_key, content, category, updated_at")
                .eq("user_id", user_id)
                .ilike("content", f"%{safe_q}%")
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )
            hits = result.data or []
            if not hits:
                result = (
                    client.table("cognitive_memories")
                    .select("mem_key, content, category, updated_at")
                    .eq("user_id", user_id)
                    .ilike("mem_key", f"%{safe_q}%")
                    .order("updated_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                hits = result.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[MEMORY] search failed %s", exc)
        hits = []

    return {
        "ok": True,
        "query": q,
        "results": [
            {
                "key": h["mem_key"],
                "content": h["content"],
                "category": h.get("category"),
            }
            for h in hits
        ],
    }


def list_memory(user_id: str, *, limit: int = 20) -> dict[str, Any]:
    result = (
        _client()
        .table("cognitive_memories")
        .select("mem_key, content, category, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = result.data or []
    return {
        "ok": True,
        "count": len(rows),
        "items": [
            {"key": r["mem_key"], "content": r["content"][:120], "category": r.get("category")}
            for r in rows
        ],
    }


def memory_context_for_voice(user_id: str, *, limit: int = 5) -> str:
    """Fragmento para inyectar al inicio de sesión."""
    data = search_memory(user_id, "", limit=limit)
    items = data.get("results") or []
    if not items:
        return ""
    lines = [f"- {i['key']}: {i['content'][:160]}" for i in items[:limit]]
    return "Memorias del usuario:\n" + "\n".join(lines)
