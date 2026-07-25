"""Metering de módulos de producción: viability / trends / opportunities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from app.services import supabase_db
from app.services.async_sync import run_sync
from app.services.supabase_client import get_supabase_admin, service_role_configured

logger = logging.getLogger(__name__)

ModuleId = Literal["viability", "trends", "opportunities"]
ChannelId = Literal["http", "voice", "chat", "other"]

MODULE_LABELS: dict[str, str] = {
    "viability": "VIABLE",
    "trends": "Tendencias",
    "opportunities": "Oportunidades",
}


def resolve_plan_snapshot(user_id: str) -> tuple[str, str]:
    """Plan + status al momento de la consulta (best-effort)."""
    try:
        sub = supabase_db.get_subscription(user_id)
    except Exception:  # noqa: BLE001
        return "unknown", "unknown"
    if not sub:
        return "no_subscription", "none"
    plan_id = str(sub.get("plan_id") or "unknown").strip().lower() or "unknown"
    status = str(sub.get("status") or "unknown").strip().lower() or "unknown"
    return plan_id, status


def log_module_usage(
    *,
    user_id: str,
    module: ModuleId,
    channel: ChannelId = "http",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Inserta una fila de uso. No lanza — el metering no debe romper el módulo."""
    uid = (user_id or "").strip()
    if not uid or module not in MODULE_LABELS:
        return None
    if not service_role_configured():
        logger.warning(
            "[MODULE-USAGE] skip — SUPABASE_SERVICE_ROLE_KEY missing module=%s",
            module,
        )
        return None

    plan_id, plan_status = resolve_plan_snapshot(uid)
    row = {
        "user_id": uid,
        "module": module,
        "plan_id": plan_id,
        "plan_status": plan_status,
        "channel": channel if channel in ("http", "voice", "chat", "other") else "other",
        "metadata": metadata or {},
    }
    try:
        client = get_supabase_admin(require_service_role=True)
        result = client.table("module_usage").insert(row).execute()
        data = (result.data or [None])[0]
        logger.info(
            "[MODULE-USAGE] module=%s user=%s plan=%s/%s channel=%s",
            module,
            uid[:8],
            plan_id,
            plan_status,
            channel,
        )
        return data if isinstance(data, dict) else row
    except Exception:  # noqa: BLE001
        logger.exception(
            "[MODULE-USAGE] insert failed module=%s user=%s",
            module,
            uid[:8],
        )
        return None


async def log_module_usage_async(
    *,
    user_id: str,
    module: ModuleId,
    channel: ChannelId = "http",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    return await run_sync(
        log_module_usage,
        user_id=user_id,
        module=module,
        channel=channel,
        metadata=metadata,
    )


def summarize_module_usage(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit_users: int = 200,
) -> dict[str, Any]:
    """Agrega conteos por módulo / plan / usuario (admin)."""
    if not service_role_configured():
        return {"ok": False, "error": "service_role_missing", "rows": []}

    client = get_supabase_admin(require_service_role=True)
    q = client.table("module_usage").select(
        "id,user_id,module,plan_id,plan_status,channel,created_at"
    )
    if since is not None:
        q = q.gte("created_at", since.astimezone(timezone.utc).isoformat())
    if until is not None:
        q = q.lt("created_at", until.astimezone(timezone.utc).isoformat())
    # Cap fetch for safety; admin can narrow window
    result = q.order("created_at", desc=True).limit(20_000).execute()
    rows = result.data or []

    by_module: dict[str, int] = {}
    by_plan: dict[str, int] = {}
    by_user_module: dict[str, dict[str, int]] = {}
    users: set[str] = set()

    for r in rows:
        mod = str(r.get("module") or "")
        plan = f"{r.get('plan_id')}:{r.get('plan_status')}"
        uid = str(r.get("user_id") or "")
        by_module[mod] = by_module.get(mod, 0) + 1
        by_plan[plan] = by_plan.get(plan, 0) + 1
        users.add(uid)
        bucket = by_user_module.setdefault(uid, {})
        bucket[mod] = bucket.get(mod, 0) + 1

    top_users = sorted(
        (
            {
                "user_id": uid,
                "total": sum(counts.values()),
                "by_module": counts,
            }
            for uid, counts in by_user_module.items()
        ),
        key=lambda x: x["total"],
        reverse=True,
    )[: max(1, limit_users)]

    return {
        "ok": True,
        "row_count": len(rows),
        "distinct_users": len(users),
        "by_module": by_module,
        "by_plan": by_plan,
        "top_users": top_users,
        "module_labels": MODULE_LABELS,
    }
