"""Monedero USD de recarga — consumo proporcional por recurso."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.plans import unit_cost_usd
from app.services import supabase_db

logger = logging.getLogger(__name__)

RESOURCE_LABELS_ES: dict[str, str] = {
    "voice_min": "voz",
    "image_std": "imágenes",
    "image_hd": "imágenes HD",
    "web_search": "búsquedas web",
    "pdf": "PDF",
    "vision": "cámara / visión",
    "advanced_turn": "modo avanzado",
    "maps_route": "mapas / navegación",
}


def wallet_balance_usd(user_id: str) -> float:
    try:
        return float(supabase_db.get_recharge_balance_usd(user_id) or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[WALLET] balance fail user=%s: %s", user_id[:8], exc)
        return 0.0


def can_afford(user_id: str, resource: str, *, units: float = 1.0) -> bool:
    cost = unit_cost_usd(resource) * max(0.0, float(units))
    if cost <= 0:
        return True
    return wallet_balance_usd(user_id) + 1e-9 >= cost


def try_spend(
    user_id: str,
    resource: str,
    *,
    units: float = 1.0,
) -> dict[str, Any]:
    """
    Debita el monedero si hay saldo. No crea saldo negativo.
    returns {ok, charged_usd, balance_usd, code?, error?}
    """
    units = max(0.0, float(units))
    unit = unit_cost_usd(resource)
    cost = round(unit * units, 4)
    if cost <= 0:
        return {
            "ok": True,
            "charged_usd": 0.0,
            "balance_usd": wallet_balance_usd(user_id),
            "resource": resource,
            "units": units,
        }

    balance = wallet_balance_usd(user_id)
    if balance + 1e-9 < cost:
        label = RESOURCE_LABELS_ES.get(resource, resource)
        return {
            "ok": False,
            "charged_usd": 0.0,
            "balance_usd": round(balance, 2),
            "resource": resource,
            "units": units,
            "code": "needs_recharge",
            "error": (
                f"Alcanzaste el límite de {label}. "
                "Recarga desde $10 para continuar (crédito proporcional al monto)."
            ),
        }

    ok = supabase_db.debit_recharge_balance(
        user_id,
        cost,
        resource=resource,
        units=units,
    )
    new_bal = wallet_balance_usd(user_id)
    if not ok:
        return {
            "ok": False,
            "charged_usd": 0.0,
            "balance_usd": round(new_bal, 2),
            "resource": resource,
            "units": units,
            "code": "wallet_debit_failed",
            "error": "No pude descontar del monedero. Intenta de nuevo o recarga.",
        }
    logger.info(
        "[WALLET] spend user=%s resource=%s units=%.4f cost=%.4f bal=%.2f",
        user_id[:8],
        resource,
        units,
        cost,
        new_bal,
    )
    return {
        "ok": True,
        "charged_usd": round(cost, 4),
        "balance_usd": round(new_bal, 2),
        "resource": resource,
        "units": units,
    }


def recharge_limit_message(resource: str) -> str:
    label = RESOURCE_LABELS_ES.get(resource, resource)
    return (
        f"Alcanzaste el límite de {label}. "
        "Recarga desde $10 para seguir — el crédito es proporcional al monto."
    )
