"""Gate de búsquedas web + monedero."""

from __future__ import annotations

from typing import Any

from app.deps.plan_access import effective_plan_limits
from app.services.wallet import can_afford, try_spend


def gate_web_search(user_id: str) -> dict[str, Any] | None:
    """
    None = permitido (cupo del plan).
    dict ok=False = bloquear con spoken/error.
    Si plan no incluye búsquedas (cap=0), cobra monedero.
    """
    limits, reason, _ = effective_plan_limits(user_id)
    cap = int(limits.web_searches_per_day)
    if cap < 0:
        return None
    if cap > 0:
        # Contador diario aún no persistido: cupo de plan se respeta en presentación;
        # no bloqueamos por conteo hasta migrar métrica.
        return None
    # cap == 0 (free_basic): solo monedero
    if can_afford(user_id, "web_search", units=1.0):
        spend = try_spend(user_id, "web_search", units=1.0)
        if spend.get("ok"):
            return None
    return {
        "ok": False,
        "spoken": (
            "Señor, alcanzó el límite de búsquedas web. "
            "Recarga desde diez dólares para continuar, o elija un plan."
        ),
        "error": "needs_recharge",
        "code": "needs_recharge",
    }
