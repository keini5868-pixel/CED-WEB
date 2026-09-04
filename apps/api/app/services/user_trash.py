"""Papelera de usuario — soft-delete con restauración y purga a 30 días."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.user_id_utils import normalize_user_id

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30

Scope = str

SCOPE_META: dict[str, dict[str, str]] = {
    "conversation": {
        "table": "voice_conversations",
        "id": "id",
        "title": "title",
        "label": "conversaciones",
        "confirm": "sí, borra todo el historial",
    },
    "image": {
        "table": "generated_images",
        "id": "id",
        "title": "prompt",
        "label": "imágenes",
        "confirm": "sí, borra todas las imágenes y pdf",
    },
    "pdf": {
        "table": "ced_pdf_artifacts",
        "id": "file_id",
        "title": "title",
        "label": "PDFs",
        "confirm": "sí, borra todas las imágenes y pdf",
    },
    "finance": {
        "table": "finance_transactions",
        "id": "id",
        "title": "description",
        "label": "movimientos de finanzas",
        "confirm": "sí, borra todo el historial de finanzas",
    },
}

# Alias de borrado masivo → uno o más scopes.
MASS_GROUPS: dict[str, tuple[str, ...]] = {
    "finance": ("finance",),
    "historial": ("conversation", "image", "pdf"),
    "conversation": ("conversation",),
    "files": ("image", "pdf"),
}

CONFIRM_PHRASES: dict[str, tuple[str, ...]] = {
    "finance": (
        "si borra todo el historial de finanzas",
        "si borra todo de finanzas",
        "si borra todos los movimientos de finanzas",
    ),
    "historial": (
        "si borra todo el historial",
        "si borra todo el historial de conversaciones",
    ),
    "conversation": (
        "si borra todas las conversaciones",
        "si borra todo el historial de conversaciones",
    ),
    "files": (
        "si borra todas las imagenes y pdf",
        "si borra todos los archivos",
        "si borra todas las imagenes y pdfs",
    ),
}

_DEL = (
    r"(?:borr(?:ar?|[aá])|elimina(?:r)?|vac[ií]a(?:r)?|limpia(?:r)?)"
)
_MASS_FINANCE = re.compile(
    rf"(?is)\b{_DEL}\b.{{0,40}}\b(?:finanzas|movimientos?\s+de\s+finanzas|historial\s+de\s+finanzas)\b",
)
_MASS_FILES = re.compile(
    rf"(?is)\b{_DEL}\b.{{0,40}}\b(?:im[aá]genes|pdfs?|archivos)\b",
)
_MASS_CONV = re.compile(
    rf"(?is)\b{_DEL}\b.{{0,40}}\bconversaciones\b",
)
_MASS_HIST = re.compile(
    rf"(?is)\b{_DEL}\b.{{0,40}}\b(?:todo\s+el\s+)?historial\b"
    r"(?!\s+de\s+finanzas)",
)
_MASS_BARE = re.compile(
    rf"(?is)\b{_DEL}\s+todo\b",
)
_CANCEL = re.compile(
    r"(?is)^\s*(?:cancelar?|cancela|no|mejor\s+no|olvida(?:lo)?)\s*[.!]?\s*$"
)
_EASY_CONFIRM = re.compile(
    r"(?is)^\s*(?:s[ií]|ok(?:ay)?|vale|dale|adelante|confirmo|hazlo|procede|"
    r"borra(?:lo)?|elim[ií]nalo)(?:\s+por\s+favor)?[\s.!,]*$"
)


def _client():
    from app.services import supabase_db

    return supabase_db._client()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _purge_after(now: datetime | None = None) -> datetime:
    return (now or _now()) + timedelta(days=RETENTION_DAYS)


def _norm(text: str) -> str:
    t = (text or "").lower().replace("í", "i").replace("á", "a").replace("é", "e")
    t = t.replace("ó", "o").replace("ú", "u").replace("ü", "u")
    t = re.sub(r"[^\wñ\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def detect_mass_delete_group(text: str, *, default_group: str | None = None) -> str | None:
    t = text or ""
    if _MASS_FINANCE.search(t):
        return "finance"
    if _MASS_FILES.search(t):
        return "files"
    if _MASS_CONV.search(t):
        return "conversation"
    if _MASS_HIST.search(t):
        return "historial"
    if default_group and _MASS_BARE.search(t):
        return default_group
    if _MASS_BARE.search(t) and re.search(r"(?is)\bfinanzas\b", t):
        return "finance"
    return None


def matches_strong_confirm(text: str, group: str) -> bool:
    n = _norm(text)
    return n in (CONFIRM_PHRASES.get(group) or ())


def matches_pending_confirm(text: str, group: str) -> bool:
    """Tras el aviso, basta un sí / dale / repetir el pedido de borrado."""
    if matches_strong_confirm(text, group):
        return True
    if _EASY_CONFIRM.match((text or "").strip()):
        return True
    if detect_mass_delete_group(text) == group:
        return True
    n = _norm(text)
    if n.startswith("si") and any(
        w in n for w in ("borra", "elimina", "confirma", "adelante", "dale")
    ):
        return True
    return False


def confirm_phrase_for(group: str) -> str:
    if group == "finance":
        return "sí, borra todo el historial de finanzas"
    if group == "files":
        return "sí, borra todas las imágenes y pdf"
    if group == "conversation":
        return "sí, borra todas las conversaciones"
    return "sí, borra todo el historial"


def _label_for_group(group: str) -> str:
    if group == "finance":
        return "todos los movimientos de finanzas"
    if group == "files":
        return "todas las imágenes y PDFs"
    if group == "conversation":
        return "todas las conversaciones"
    return "todo el historial (conversaciones, imágenes y PDFs)"


def _row_title(scope: str, row: dict[str, Any]) -> str:
    meta = SCOPE_META[scope]
    raw = str(row.get(meta["title"]) or "").strip()
    if scope == "finance":
        kind = str(row.get("type") or "")
        amount = row.get("amount")
        desc = raw or kind
        if amount is not None:
            return f"{desc} · {amount}"
        return desc or "Movimiento"
    return raw or meta["label"]


def _select_cols(scope: str) -> str:
    meta = SCOPE_META[scope]
    cols = [meta["id"], meta["title"], "deleted_at", "purge_after", "created_at"]
    if scope == "finance":
        cols.extend(["type", "amount", "currency", "occurred_on"])
    if scope == "image":
        cols.append("public_url")
    if scope == "pdf":
        cols.append("filename")
    if scope == "conversation":
        cols.extend(["channel", "updated_at"])
    return ", ".join(dict.fromkeys(cols))


def _ids_of(scope: str, rows: list[dict[str, Any]]) -> list[str]:
    key = SCOPE_META[scope]["id"]
    return [str(r.get(key) or "") for r in rows if r.get(key)]


def trash_items(user_id: str, scope: str, ids: list[str]) -> dict[str, Any]:
    """Envía ítems a la papelera (no borra en duro)."""
    if scope not in SCOPE_META:
        return {"ok": False, "error": "invalid_scope", "count": 0}
    uid = normalize_user_id(user_id)
    clean = [i.strip() for i in ids if str(i).strip()]
    if not clean:
        return {"ok": True, "count": 0, "scope": scope}
    meta = SCOPE_META[scope]
    now = _now()
    payload = {
        "deleted_at": now.isoformat(),
        "purge_after": _purge_after(now).isoformat(),
    }
    try:
        _client().table(meta["table"]).update(payload).eq("user_id", uid).in_(
            meta["id"], clean
        ).is_("deleted_at", "null").execute()
        return {"ok": True, "count": len(clean), "scope": scope}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[TRASH] trash_items failed scope=%s", scope)
        return {"ok": False, "error": str(exc)[:160], "count": 0}


def restore_items(user_id: str, scope: str, ids: list[str]) -> dict[str, Any]:
    if scope not in SCOPE_META:
        return {"ok": False, "error": "invalid_scope", "count": 0}
    uid = normalize_user_id(user_id)
    clean = [i.strip() for i in ids if str(i).strip()]
    if not clean:
        return {"ok": True, "count": 0, "scope": scope}
    meta = SCOPE_META[scope]
    try:
        _client().table(meta["table"]).update(
            {"deleted_at": None, "purge_after": None}
        ).eq("user_id", uid).in_(meta["id"], clean).execute()
        return {"ok": True, "count": len(clean), "scope": scope}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[TRASH] restore failed scope=%s", scope)
        return {"ok": False, "error": str(exc)[:160], "count": 0}


def purge_items(user_id: str, scope: str, ids: list[str]) -> dict[str, Any]:
    """Borrado definitivo (solo ítems ya en papelera)."""
    if scope not in SCOPE_META:
        return {"ok": False, "error": "invalid_scope", "count": 0}
    uid = normalize_user_id(user_id)
    clean = [i.strip() for i in ids if str(i).strip()]
    if not clean:
        return {"ok": True, "count": 0, "scope": scope}
    meta = SCOPE_META[scope]
    try:
        _client().table(meta["table"]).delete().eq("user_id", uid).in_(
            meta["id"], clean
        ).not_.is_("deleted_at", "null").execute()
        return {"ok": True, "count": len(clean), "scope": scope}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[TRASH] purge failed scope=%s", scope)
        return {"ok": False, "error": str(exc)[:160], "count": 0}


def _active_ids(user_id: str, scope: str, *, limit: int = 2000) -> list[str]:
    meta = SCOPE_META[scope]
    uid = normalize_user_id(user_id)
    result = (
        _client()
        .table(meta["table"])
        .select(meta["id"])
        .eq("user_id", uid)
        .is_("deleted_at", "null")
        .limit(limit)
        .execute()
    )
    return _ids_of(scope, list(result.data or []))


def trash_group(user_id: str, group: str) -> dict[str, Any]:
    scopes = MASS_GROUPS.get(group)
    if not scopes:
        return {"ok": False, "error": "invalid_group", "count": 0}
    total = 0
    details: list[dict[str, Any]] = []
    for scope in scopes:
        ids = _active_ids(user_id, scope)
        if not ids:
            details.append({"scope": scope, "count": 0})
            continue
        out = trash_items(user_id, scope, ids)
        n = int(out.get("count") or 0)
        total += n
        details.append({"scope": scope, "count": n})
    return {"ok": True, "count": total, "group": group, "details": details}


def list_trash(user_id: str, *, scope: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    purge_expired(user_id)
    uid = normalize_user_id(user_id)
    scopes = (scope,) if scope and scope in SCOPE_META else tuple(SCOPE_META)
    out: list[dict[str, Any]] = []
    for sc in scopes:
        meta = SCOPE_META[sc]
        try:
            result = (
                _client()
                .table(meta["table"])
                .select(_select_cols(sc))
                .eq("user_id", uid)
                .not_.is_("deleted_at", "null")
                .order("deleted_at", desc=True)
                .limit(max(1, min(limit, 200)))
                .execute()
            )
        except Exception:  # noqa: BLE001
            logger.warning("[TRASH] list failed scope=%s", sc)
            continue
        for row in result.data or []:
            item_id = str(row.get(meta["id"]) or "")
            if not item_id:
                continue
            out.append(
                {
                    "id": item_id,
                    "scope": sc,
                    "title": _row_title(sc, row),
                    "deleted_at": row.get("deleted_at"),
                    "purge_after": row.get("purge_after"),
                    "preview": str(row.get("public_url") or row.get("filename") or "")[:200]
                    or None,
                }
            )
    out.sort(key=lambda r: str(r.get("deleted_at") or ""), reverse=True)
    return out[: max(1, min(limit, 200))]


def purge_expired(user_id: str | None = None) -> int:
    """Elimina en duro lo que ya cumplió los 30 días."""
    now_iso = _now().isoformat()
    deleted = 0
    for scope, meta in SCOPE_META.items():
        try:
            q = (
                _client()
                .table(meta["table"])
                .delete()
                .lte("purge_after", now_iso)
                .not_.is_("deleted_at", "null")
            )
            if user_id:
                q = q.eq("user_id", normalize_user_id(user_id))
            q.execute()
            deleted += 1
        except Exception:  # noqa: BLE001
            logger.warning("[TRASH] purge_expired failed scope=%s", scope)
    return deleted


def _commit_trash(user_id: str, group: str) -> dict[str, Any]:
    from app.services import voice_client_session as vcs

    result = trash_group(user_id, group)
    vcs.clear_trash_pending(user_id)
    n = int(result.get("count") or 0)
    if n <= 0:
        return {
            "spoken": "No había nada activo que enviar a la papelera, señor.",
            "deleted": 0,
            "trashed": 0,
            "group": group,
        }
    return {
        "spoken": (
            f"Listo. Envié {n} elemento(s) a la papelera. "
            "Puede restaurarlos durante 30 días; después se eliminan solos."
        ),
        "deleted": n,
        "trashed": n,
        "group": group,
    }


def try_trash_turn(
    user_id: str | None,
    text: str,
    *,
    default_group: str | None = None,
) -> dict[str, Any] | None:
    """Borrado masivo: un aviso y un «sí» (o repetir el pedido). Va a papelera 30 días."""
    if not user_id or not (text or "").strip():
        return None
    from app.services import voice_client_session as vcs

    pending = vcs.get_trash_pending(user_id)
    group = detect_mass_delete_group(text, default_group=default_group)

    if pending:
        pending_group = str(pending.get("group") or "")
        if _CANCEL.match((text or "").strip()):
            vcs.clear_trash_pending(user_id)
            return {"spoken": "Cancelado, señor. No borré nada."}
        if matches_pending_confirm(text, pending_group):
            return _commit_trash(user_id, pending_group)
        if group and group != pending_group:
            vcs.set_trash_pending(user_id, {"group": group})
            return {
                "spoken": (
                    f"Esto enviará {_label_for_group(group)} a la papelera "
                    f"(30 días para recuperar). ¿Seguro? Diga sí o cancelar."
                ),
                "needs_confirm": True,
                "group": group,
            }
        return {
            "spoken": "¿Seguro? Diga sí para enviar a la papelera, o cancelar.",
            "needs_confirm": True,
            "group": pending_group,
        }

    if not group:
        if _MASS_BARE.search(text or ""):
            return {
                "spoken": (
                    "¿Qué envío a la papelera, señor: el historial o finanzas? "
                    "Diga «borra todo el historial» o «borra todo de finanzas»."
                )
            }
        return None
    if matches_strong_confirm(text, group):
        return _commit_trash(user_id, group)
    vcs.set_trash_pending(user_id, {"group": group})
    return {
        "spoken": (
            f"Esto enviará {_label_for_group(group)} a la papelera "
            f"(se puede restaurar 30 días). ¿Seguro? Diga sí o cancelar."
        ),
        "needs_confirm": True,
        "group": group,
    }
