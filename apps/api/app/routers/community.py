"""Sala CED — API autenticada."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import community_forum as forum

router = APIRouter(prefix="/v1/community", tags=["community"])


class TokenBody(BaseModel):
    token: str = Field(min_length=2, max_length=32)


class PostBody(BaseModel):
    room: str
    title: str = ""
    body: str = Field(min_length=1, max_length=1200)
    token: str = ""


class ReplyBody(BaseModel):
    body: str = Field(min_length=1, max_length=1200)
    token: str = ""


class ReactBody(BaseModel):
    token: str


class ReportBody(BaseModel):
    reason: str = "report"


@router.get("/meta")
def get_meta(user_id: str = Depends(require_user_id)) -> dict:
    return forum.meta(user_id)


@router.patch("/me")
def patch_me(body: TokenBody, user_id: str = Depends(require_user_id)) -> dict:
    result = forum.set_token(user_id, body.token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/posts")
def get_posts(
    user_id: str = Depends(require_user_id),
    room: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=80),
) -> dict:
    result = forum.list_posts(user_id, room, limit)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/posts")
def post_create(body: PostBody, user_id: str = Depends(require_user_id)) -> dict:
    result = forum.create_post(
        user_id,
        room=body.room,
        title=body.title,
        body=body.body,
        token=body.token,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/posts/{post_id}/replies")
def post_reply(
    post_id: str,
    body: ReplyBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    result = forum.create_reply(user_id, post_id, body.body, body.token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/posts/{post_id}/react")
def post_react(
    post_id: str,
    body: ReactBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    result = forum.react(user_id, post_id, body.token)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/posts/{post_id}/report")
def post_report(
    post_id: str,
    body: ReportBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    return forum.report_post(user_id, post_id, body.reason)
