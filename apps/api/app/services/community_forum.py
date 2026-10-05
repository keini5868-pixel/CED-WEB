"""Sala CED — foro de prompts, guiones, copies y ayuda. Sin DMs."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.community_guard import (
    POST_COOLDOWN_SEC,
    REPLY_COOLDOWN_SEC,
    ROOMS,
    TOKENS,
    normalize_room,
    normalize_token,
    public_display_name,
    reject_reason,
)
from app.services.supabase_db import _client

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DB_OK: bool | None = None
_MEM_POSTS: list[dict[str, Any]] = []
_MEM_REPLIES: list[dict[str, Any]] = []
_MEM_PROFILES: dict[str, dict[str, Any]] = {}
_MEM_LAST_POST: dict[str, datetime] = {}
_MEM_LAST_REPLY: dict[str, datetime] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value or "")


def _use_db() -> bool:
    global _DB_OK
    if _DB_OK is not None:
        return _DB_OK
    try:
        _client().table("community_posts").select("id").limit(1).execute()
        _DB_OK = True
    except Exception:
        logger.warning("Sala CED: tabla ausente, usando memoria de proceso.")
        _DB_OK = False
    return _DB_OK


def _profile_name(user_id: str) -> str:
    try:
        res = (
            _client()
            .table("profiles")
            .select("full_name, email")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        row = (res.data or [None])[0] or {}
        return public_display_name(row.get("full_name"), row.get("email"))
    except Exception:
        mem = _MEM_PROFILES.get(user_id) or {}
        return public_display_name(mem.get("full_name"), mem.get("email"))


def _get_or_create_me(user_id: str) -> dict[str, Any]:
    if _use_db():
        try:
            res = (
                _client()
                .table("community_profiles")
                .select("user_id, token, created_at")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                row = rows[0]
                return {
                    "user_id": user_id,
                    "token": row.get("token") or "",
                    "display_name": _profile_name(user_id),
                    "created_at": _iso(row.get("created_at")),
                }
        except Exception as exc:
            logger.warning("community profile read: %s", exc)
    with _LOCK:
        mem = _MEM_PROFILES.get(user_id)
        if mem:
            return {
                "user_id": user_id,
                "token": mem.get("token") or "",
                "display_name": _profile_name(user_id),
                "created_at": _iso(mem.get("created_at")),
            }
    return {
        "user_id": user_id,
        "token": "",
        "display_name": _profile_name(user_id),
        "created_at": "",
    }


def set_token(user_id: str, token: str) -> dict[str, Any]:
    chosen = normalize_token(token)
    if not chosen:
        return {"ok": False, "error": "Elige una ficha CED."}
    now = _now()
    if _use_db():
        try:
            _client().table("community_profiles").upsert(
                {"user_id": user_id, "token": chosen, "updated_at": now.isoformat()},
            ).execute()
        except Exception as exc:
            logger.warning("community profile upsert: %s", exc)
    with _LOCK:
        prev = _MEM_PROFILES.get(user_id) or {}
        _MEM_PROFILES[user_id] = {
            **prev,
            "token": chosen,
            "created_at": prev.get("created_at") or now,
            "updated_at": now,
        }
    me = _get_or_create_me(user_id)
    me["token"] = chosen
    return {"ok": True, "me": me}


def meta(user_id: str) -> dict[str, Any]:
    return {
        "ok": True,
        "rooms": [
            {"id": "prompts", "label": "Prompts", "hint": "Lo que le pides a CED"},
            {"id": "guiones", "label": "Guiones / video", "hint": "Historias y piezas"},
            {"id": "copies", "label": "Copies", "hint": "Textos que ya funcionaron"},
            {"id": "ayuda", "label": "Ayuda", "hint": "Dudas del producto"},
        ],
        "tokens": [{"id": t, "src": f"/community/tokens/{t}.jpg"} for t in TOKENS],
        "rules": [
            "Sin teléfonos, WhatsApp ni ‘te contacto’.",
            "Solo enlaces de YouTube o ced-castillo.com.",
            "No publiques chats de clientes ni precios de entrada.",
            "No hay privado. La ayuda se queda en la sala.",
        ],
        "me": _get_or_create_me(user_id),
        "persistence": "db" if _use_db() else "memory",
    }


def _cooldown_ok(bucket: dict[str, datetime], user_id: str, seconds: int) -> str | None:
    last = bucket.get(user_id)
    if not last:
        return None
    wait = seconds - (_now() - last).total_seconds()
    if wait > 0:
        return f"Espera {int(wait)} s para no saturar la sala."
    return None


def _serialize_post(row: dict[str, Any], replies: list[dict[str, Any]]) -> dict[str, Any]:
    reactions = row.get("reactions") or {}
    if isinstance(reactions, str):
        reactions = {}
    return {
        "id": row["id"],
        "room": row["room"],
        "title": row.get("title") or "",
        "body": row["body"],
        "token": row.get("token") or "listo",
        "display_name": row.get("display_name") or "Operador",
        "mine": bool(row.get("mine")),
        "created_at": _iso(row.get("created_at")),
        "reactions": reactions,
        "replies": replies,
        "reply_count": len(replies),
    }


def list_posts(user_id: str, room: str | None, limit: int = 40) -> dict[str, Any]:
    room_id = normalize_room(room or "") if room else None
    if room and not room_id:
        return {"ok": False, "error": "Sala desconocida."}
    if _use_db():
        try:
            q = (
                _client()
                .table("community_posts")
                .select("*")
                .eq("hidden", False)
                .order("created_at", desc=True)
                .limit(min(limit, 80))
            )
            if room_id:
                q = q.eq("room", room_id)
            posts = q.execute().data or []
            ids = [p["id"] for p in posts]
            replies: list[dict[str, Any]] = []
            if ids:
                replies = (
                    _client()
                    .table("community_replies")
                    .select("*")
                    .in_("post_id", ids)
                    .eq("hidden", False)
                    .order("created_at", desc=False)
                    .execute()
                    .data
                    or []
                )
            by_post: dict[str, list[dict[str, Any]]] = {i: [] for i in ids}
            for reply in replies:
                by_post.setdefault(reply["post_id"], []).append(
                    {
                        "id": reply["id"],
                        "body": reply["body"],
                        "token": reply.get("token") or "listo",
                        "display_name": reply.get("display_name") or "Operador",
                        "mine": reply.get("user_id") == user_id,
                        "created_at": _iso(reply.get("created_at")),
                    }
                )
            items = []
            for post in posts:
                post["mine"] = post.get("user_id") == user_id
                items.append(_serialize_post(post, by_post.get(post["id"], [])))
            return {"ok": True, "posts": items}
        except Exception as exc:
            logger.warning("community list db: %s", exc)
    with _LOCK:
        posts = [p for p in _MEM_POSTS if not p.get("hidden")]
        if room_id:
            posts = [p for p in posts if p["room"] == room_id]
        posts = sorted(posts, key=lambda p: p["created_at"], reverse=True)[:limit]
        items = []
        for post in posts:
            replies = [
                {
                    "id": r["id"],
                    "body": r["body"],
                    "token": r.get("token") or "listo",
                    "display_name": r.get("display_name") or "Operador",
                    "mine": r.get("user_id") == user_id,
                    "created_at": _iso(r.get("created_at")),
                }
                for r in _MEM_REPLIES
                if r["post_id"] == post["id"] and not r.get("hidden")
            ]
            row = {**post, "mine": post.get("user_id") == user_id}
            items.append(_serialize_post(row, replies))
    return {"ok": True, "posts": items}


def create_post(
    user_id: str,
    *,
    room: str,
    title: str,
    body: str,
    token: str,
) -> dict[str, Any]:
    room_id = normalize_room(room)
    if not room_id:
        return {"ok": False, "error": "Elige una sala."}
    me = _get_or_create_me(user_id)
    chosen = normalize_token(token) or normalize_token(me.get("token") or "") or "listo"
    title_clean = (title or "").strip()[:80]
    reason = reject_reason(f"{title_clean}\n{body}")
    if reason:
        return {"ok": False, "error": reason}
    with _LOCK:
        wait = _cooldown_ok(_MEM_LAST_POST, user_id, POST_COOLDOWN_SEC)
        if wait:
            return {"ok": False, "error": wait}
    now = _now()
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "room": room_id,
        "title": title_clean,
        "body": body.strip(),
        "token": chosen,
        "display_name": me["display_name"],
        "reactions": {},
        "hidden": False,
        "created_at": now,
    }
    if _use_db():
        try:
            payload = {
                **row,
                "created_at": now.isoformat(),
                "reactions": {},
            }
            _client().table("community_posts").insert(payload).execute()
        except Exception as exc:
            logger.warning("community insert db: %s", exc)
    with _LOCK:
        _MEM_POSTS.insert(0, row)
        _MEM_LAST_POST[user_id] = now
        if not me.get("token"):
            _MEM_PROFILES.setdefault(user_id, {})["token"] = chosen
    row["mine"] = True
    return {"ok": True, "post": _serialize_post(row, [])}


def create_reply(user_id: str, post_id: str, body: str, token: str) -> dict[str, Any]:
    reason = reject_reason(body)
    if reason:
        return {"ok": False, "error": reason}
    me = _get_or_create_me(user_id)
    chosen = normalize_token(token) or normalize_token(me.get("token") or "") or "listo"
    with _LOCK:
        wait = _cooldown_ok(_MEM_LAST_REPLY, user_id, REPLY_COOLDOWN_SEC)
        if wait:
            return {"ok": False, "error": wait}
        exists = any(p["id"] == post_id and not p.get("hidden") for p in _MEM_POSTS)
    if _use_db() and not exists:
        try:
            found = (
                _client()
                .table("community_posts")
                .select("id")
                .eq("id", post_id)
                .eq("hidden", False)
                .limit(1)
                .execute()
                .data
            )
            exists = bool(found)
        except Exception:
            exists = False
    if not exists:
        return {"ok": False, "error": "Ese hilo ya no está."}
    now = _now()
    row = {
        "id": str(uuid.uuid4()),
        "post_id": post_id,
        "user_id": user_id,
        "body": body.strip(),
        "token": chosen,
        "display_name": me["display_name"],
        "hidden": False,
        "created_at": now,
    }
    if _use_db():
        try:
            _client().table("community_replies").insert(
                {**row, "created_at": now.isoformat()}
            ).execute()
        except Exception as exc:
            logger.warning("community reply db: %s", exc)
    with _LOCK:
        _MEM_REPLIES.append(row)
        _MEM_LAST_REPLY[user_id] = now
    return {
        "ok": True,
        "reply": {
            "id": row["id"],
            "body": row["body"],
            "token": row["token"],
            "display_name": row["display_name"],
            "mine": True,
            "created_at": _iso(now),
        },
    }


def react(user_id: str, post_id: str, token: str) -> dict[str, Any]:
    chosen = normalize_token(token)
    if not chosen:
        return {"ok": False, "error": "Ficha desconocida."}
    reactions: dict[str, int] = {}
    if _use_db():
        try:
            res = (
                _client()
                .table("community_posts")
                .select("reactions")
                .eq("id", post_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                reactions = dict(rows[0].get("reactions") or {})
                reactions[chosen] = int(reactions.get(chosen) or 0) + 1
                _client().table("community_posts").update({"reactions": reactions}).eq(
                    "id", post_id
                ).execute()
        except Exception as exc:
            logger.warning("community react db: %s", exc)
    with _LOCK:
        for post in _MEM_POSTS:
            if post["id"] == post_id:
                current = dict(post.get("reactions") or {})
                current[chosen] = int(current.get(chosen) or 0) + 1
                post["reactions"] = current
                reactions = current
                break
    return {"ok": True, "reactions": reactions}


def report_post(user_id: str, post_id: str, reason: str) -> dict[str, Any]:
    note = (reason or "report").strip()[:200]
    if _use_db():
        try:
            _client().table("community_reports").insert(
                {
                    "id": str(uuid.uuid4()),
                    "post_id": post_id,
                    "user_id": user_id,
                    "reason": note,
                    "created_at": _now().isoformat(),
                }
            ).execute()
            count = (
                _client()
                .table("community_reports")
                .select("id", count="exact")
                .eq("post_id", post_id)
                .execute()
            )
            n = getattr(count, "count", None) or len(count.data or [])
            if n >= 3:
                _client().table("community_posts").update({"hidden": True}).eq(
                    "id", post_id
                ).execute()
        except Exception as exc:
            logger.warning("community report db: %s", exc)
    with _LOCK:
        for post in _MEM_POSTS:
            if post["id"] == post_id:
                post["reports"] = int(post.get("reports") or 0) + 1
                if post["reports"] >= 3:
                    post["hidden"] = True
    return {"ok": True}


def reset_for_tests() -> None:
    global _DB_OK
    with _LOCK:
        _MEM_POSTS.clear()
        _MEM_REPLIES.clear()
        _MEM_PROFILES.clear()
        _MEM_LAST_POST.clear()
        _MEM_LAST_REPLY.clear()
        _DB_OK = False
