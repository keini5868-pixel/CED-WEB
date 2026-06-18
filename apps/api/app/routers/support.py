"""Chat de soporte — endpoints usuario y admin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.deps.auth import is_super_admin, require_auth_user, require_super_admin
from app.config import get_settings
from app.services import support_chat as svc
from app.services.support_media import (
    _EXT_BY_MIME,
    decode_support_upload,
    store_support_attachment,
    support_attachment_client_url,
    support_attachment_path,
)

router = APIRouter(prefix="/v1/support", tags=["support"])

_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class CreateConversationBody(BaseModel):
    category: str = Field(description="bug | idea | question | other")


class SendMessageBody(BaseModel):
    content: str = Field(default="", max_length=8000)
    attachments: list[str] = Field(default_factory=list)


class UpdateStatusBody(BaseModel):
    status: str = Field(description="open | in_progress | resolved")


async def _auth_context(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await require_auth_user(authorization)


@router.get("/status")
async def support_status() -> dict[str, bool]:
    """Público — indica si el chat de soporte está activo en API."""
    return {"ok": True, "enabled": get_settings().support_chat_enabled}


@router.post("/conversations")
async def create_conversation(
    body: CreateConversationBody,
    user: dict[str, Any] = Depends(_auth_context),
) -> dict[str, Any]:
    conv = svc.create_conversation(user["id"], body.category)
    return {"ok": True, "conversation": conv}


@router.get("/conversations")
async def list_user_conversations(
    user: dict[str, Any] = Depends(_auth_context),
) -> dict[str, Any]:
    items = svc.list_user_conversations(user["id"])
    return {"ok": True, "conversations": items}


@router.get("/admin/conversations")
async def list_admin_conversations(
    status: str | None = None,
    category: str | None = None,
    unread: bool = False,
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    items = svc.list_admin_conversations(
        status=status,
        category=category,
        unread_only=unread,
    )
    return {"ok": True, "conversations": items}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    user: dict[str, Any] = Depends(_auth_context),
) -> dict[str, Any]:
    svc.assert_conversation_access(
        conversation_id,
        user_id=user["id"],
        email=user.get("email"),
        role=user.get("role"),
    )
    messages = svc.list_messages(conversation_id)
    return {"ok": True, "messages": messages}


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageBody,
    user: dict[str, Any] = Depends(_auth_context),
) -> dict[str, Any]:
    admin = is_super_admin(user.get("email"), user.get("role"))
    conv = svc.assert_conversation_access(
        conversation_id,
        user_id=user["id"],
        email=user.get("email"),
        role=user.get("role"),
        admin=admin,
    )
    sender_type = "admin" if admin and str(conv["user_id"]) != user["id"] else "user"
    if sender_type == "user" and str(conv["user_id"]) != user["id"]:
        raise HTTPException(status_code=403, detail="Sin acceso")
    message = svc.add_message(
        conversation_id,
        sender_id=user["id"],
        sender_type=sender_type,
        content=body.content,
        attachments=body.attachments,
    )
    return {"ok": True, "message": message}


@router.post("/conversations/{conversation_id}/attachments")
async def upload_attachment(
    conversation_id: str,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(_auth_context),
) -> dict[str, Any]:
    conv = svc.assert_conversation_access(
        conversation_id,
        user_id=user["id"],
        email=user.get("email"),
        role=user.get("role"),
    )
    is_admin = is_super_admin(user.get("email"), user.get("role"))
    if str(conv["user_id"]) != user["id"] and not is_admin:
        raise HTTPException(status_code=403, detail="Sin acceso")
    raw = await file.read()
    mime = (file.content_type or "image/jpeg").split(";")[0].strip()
    try:
        image_bytes, mime = decode_support_upload(raw, mime)
        file_name = store_support_attachment(user["id"], conversation_id, image_bytes, mime)
        url = support_attachment_client_url(file_name)
        return {"ok": True, "url": url, "file_name": file_name}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/attachments/{file_name}")
async def serve_attachment(
    file_name: str,
    user: dict[str, Any] = Depends(_auth_context),
) -> FileResponse:
    admin = is_super_admin(user.get("email"), user.get("role"))
    if not svc.user_owns_attachment(user["id"], file_name, admin=admin):
        raise HTTPException(status_code=403, detail="Sin acceso al archivo")
    path = support_attachment_path(file_name)
    if not path:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    ext = path.suffix.lower()
    media_type = _MIME.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.patch("/conversations/{conversation_id}/read")
async def mark_conversation_read(
    conversation_id: str,
    user: dict[str, Any] = Depends(_auth_context),
) -> dict[str, Any]:
    admin = is_super_admin(user.get("email"), user.get("role"))
    conv = svc.assert_conversation_access(
        conversation_id,
        user_id=user["id"],
        email=user.get("email"),
        role=user.get("role"),
        admin=admin,
    )
    reader = "admin" if admin and str(conv["user_id"]) != user["id"] else "user"
    svc.mark_read(conversation_id, reader=reader)
    return {"ok": True}


@router.patch("/admin/conversations/{conversation_id}/status")
async def admin_update_status(
    conversation_id: str,
    body: UpdateStatusBody,
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    if not svc.get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = svc.update_status(conversation_id, body.status)
    return {"ok": True, "conversation": conv}


@router.get("/admin/unread-count")
async def admin_unread_count(_admin_id: str = Depends(require_super_admin)) -> dict[str, Any]:
    return {"ok": True, "count": svc.count_unread_for_admin()}


@router.get("/user/unread-count")
async def user_unread_count(user: dict[str, Any] = Depends(_auth_context)) -> dict[str, Any]:
    return {"ok": True, "count": svc.count_unread_for_user(user["id"])}
