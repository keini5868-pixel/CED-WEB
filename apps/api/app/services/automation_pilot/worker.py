"""Worker async — procesa eventos fuera del request HTTP del webhook."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.services.automation_pilot.engine import execute_matched
from app.services.automation_pilot.gate import automation_module_enabled

logger = logging.getLogger(__name__)


def enqueue_meta_event(event: dict[str, Any]) -> None:
    """ACK rápido en webhook; el trabajo corre en hilo daemon."""
    if not automation_module_enabled():
        logger.info("[AUTOMATION] skip event — module disabled")
        return
    threading.Thread(
        target=_process_meta_event,
        args=(event,),
        daemon=True,
        name="automation-meta-event",
    ).start()


def _process_meta_event(event: dict[str, Any]) -> None:
    try:
        channel = str(event.get("channel") or "")
        user_id = str(event.get("user_id") or "")
        event_type = str(event.get("event_type") or "")
        contact_id = str(event.get("contact_id") or "")
        text = str(event.get("text") or "")
        if not (channel and user_id and event_type and contact_id):
            logger.warning("[AUTOMATION] incomplete event keys=%s", list(event.keys()))
            return
        results = execute_matched(
            user_id=user_id,
            channel=channel,
            event_type=event_type,
            contact_id=contact_id,
            text=text,
            payload=event.get("raw") or {},
            media_id=event.get("media_id"),
            display_name=event.get("display_name"),
        )
        logger.info(
            "[AUTOMATION] processed channel=%s type=%s matches=%s dry=%s",
            channel,
            event_type,
            len(results),
            (results[0]["result"].get("dry_run") if results else None),
        )
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] worker failed")
