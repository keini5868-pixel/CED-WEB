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
from app.services.conversation_memory import (
    format_recall_for_voice,
    recall_previous_conversations,
    save_long_term_memory,
)
from app.services.user_address import sync_address_from_memory_key

router = APIRouter(prefix="/v1/memory", tags=["memory"])


class SaveMemoryBody(BaseModel):
    key: str = Field(max_length=120)
    content: str = Field(max_length=4000)
    category: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = None


class SearchMemoryBody(BaseModel):
    query: str = Field(default="", max_length=300)


class RecallConversationsBody(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    days_back: int = Field(default=30, ge=1, le=365)


class LongTermMemoryBody(BaseModel):
    category: str = Field(max_length=40)
    key: str = Field(max_length=120)
    value: str = Field(max_length=4000)
    importance: int = Field(default=5, ge=1, le=10)
    source_session_id: str | None = None


@router.post("/save")
async def memory_save(
    body: SaveMemoryBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        result = save_memory(
            user_id,
            body.key,
            body.content,
            category=body.category,
            tags=body.tags,
        )
        if result.get("ok"):
            sync_address_from_memory_key(user_id, body.key, body.content)
        return result
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


@router.post("/recall-conversations")
async def memory_recall_conversations(
    body: RecallConversationsBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    data = recall_previous_conversations(
        user_id,
        body.query,
        days_back=body.days_back,
    )
    data["spoken"] = format_recall_for_voice(data)
    return data


@router.post("/long-term/save")
async def memory_long_term_save(
    body: LongTermMemoryBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    return save_long_term_memory(
        user_id,
        category=body.category,
        key=body.key,
        value=body.value,
        importance=body.importance,
        source_session_id=body.source_session_id,
    )
