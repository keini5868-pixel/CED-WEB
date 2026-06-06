"""Memoria cognitiva — endpoints REST."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.cognitive_memory import (
    get_memory,
    list_memory,
    save_memory,
    search_memory,
)

router = APIRouter(prefix="/v1/memory", tags=["memory"])


class SaveMemoryBody(BaseModel):
    key: str = Field(max_length=120)
    content: str = Field(max_length=4000)
    category: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = None


class SearchMemoryBody(BaseModel):
    query: str = Field(default="", max_length=300)


@router.post("/save")
async def memory_save(
    body: SaveMemoryBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return save_memory(
            user_id,
            body.key,
            body.content,
            category=body.category,
            tags=body.tags,
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/get")
async def memory_get(
    key: str,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return get_memory(user_id, key)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/search")
async def memory_search(
    body: SearchMemoryBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    return search_memory(user_id, body.query)


@router.get("/list")
async def memory_list_route(
    user_id: str = Depends(require_user_id),
) -> dict:
    return list_memory(user_id)
