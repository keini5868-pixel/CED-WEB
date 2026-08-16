"""Papelera — enviar, listar, restaurar y borrar en duro."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.user_trash import (
    SCOPE_META,
    list_trash,
    purge_items,
    restore_items,
    trash_items,
)

router = APIRouter(prefix="/v1/trash", tags=["trash"])


class TrashBody(BaseModel):
    scope: str = Field(description="conversation | image | pdf | finance")
    ids: list[str] = Field(default_factory=list, max_length=200)


class TrashGroupBody(BaseModel):
    group: str = Field(description="finance | historial | conversation | files")


@router.get("")
def get_trash(
    user_id: str = Depends(require_user_id),
    scope: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
) -> dict:
    if scope and scope not in SCOPE_META:
        raise HTTPException(status_code=400, detail="scope inválido")
    items = list_trash(user_id, scope=scope, limit=limit)
    return {"ok": True, "items": items, "retention_days": 30}


@router.post("")
def post_trash(body: TrashBody, user_id: str = Depends(require_user_id)) -> dict:
    if body.scope not in SCOPE_META:
        raise HTTPException(status_code=400, detail="scope inválido")
    result = trash_items(user_id, body.scope, body.ids)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "trash_failed")
    return result


@router.post("/restore")
def post_restore(body: TrashBody, user_id: str = Depends(require_user_id)) -> dict:
    if body.scope not in SCOPE_META:
        raise HTTPException(status_code=400, detail="scope inválido")
    result = restore_items(user_id, body.scope, body.ids)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "restore_failed")
    return result


@router.post("/purge")
def post_purge(body: TrashBody, user_id: str = Depends(require_user_id)) -> dict:
    if body.scope not in SCOPE_META:
        raise HTTPException(status_code=400, detail="scope inválido")
    result = purge_items(user_id, body.scope, body.ids)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "purge_failed")
    return result


@router.post("/empty")
def post_empty(body: TrashGroupBody, user_id: str = Depends(require_user_id)) -> dict:
    """Vacía la papelera (borrado definitivo) de un grupo — no el historial activo."""
    from app.services.user_trash import MASS_GROUPS, list_trash, purge_items

    scopes = MASS_GROUPS.get(body.group)
    if not scopes:
        raise HTTPException(status_code=400, detail="grupo inválido")
    total = 0
    for scope in scopes:
        rows = list_trash(user_id, scope=scope, limit=200)
        ids = [str(r.get("id") or "") for r in rows if r.get("id")]
        if ids:
            out = purge_items(user_id, scope, ids)
            total += int(out.get("count") or 0)
    return {"ok": True, "count": total, "group": body.group}
