"""Producto único CED Élite — planes y límites."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlanId(StrEnum):
    ELITE_FOUNDING = "elite_founding"
    ELITE_REGULAR = "elite_regular"


FOUNDING_MEMBER_MAX_SLOTS = 50
TRIAL_DAYS = 7
USAGE_WARNING_PERCENT = 80

GEMINI_COST_PER_HOUR_USD = 1.50
RECHARGE_MARGIN_KEINI = 0.40
RECHARGE_CLIENT_SHARE = 0.60
RECHARGE_MIN_USD = 5
RECHARGE_MAX_USD = 500
RECHARGE_QUICK_AMOUNTS_USD = (10, 25, 50, 100)


@dataclass(frozen=True)
class CedEliteProduct:
    """Un solo producto; dos fases de precio."""

    gemini_minutes_per_day: int = 120
    video_allowed: bool = True
    claude_text_unlimited: bool = True
    ai_images_per_month: int = 100
    tts_elevenlabs: bool = True
    whisper_transcription: bool = True
    memory_unlimited: bool = True
    folders_unlimited: bool = True
    pdfs_unlimited: bool = True
    hud_panels_live: bool = True
    pwa_mobile: bool = True
    priority_support: bool = True
    early_access_features: bool = True


CED_ELITE = CedEliteProduct()

PLAN_PRICES_USD: dict[PlanId, int] = {
    PlanId.ELITE_FOUNDING: 149,
    PlanId.ELITE_REGULAR: 249,
}


def quote_recharge(amount_usd: float) -> dict[str, float | bool]:
    """Calcula saldo de uso y horas extra para una recarga flexible."""
    paid = max(RECHARGE_MIN_USD, min(RECHARGE_MAX_USD, float(amount_usd)))
    client_balance = paid * RECHARGE_CLIENT_SHARE
    margin_keini = paid * RECHARGE_MARGIN_KEINI
    extra_hours = client_balance / GEMINI_COST_PER_HOUR_USD if GEMINI_COST_PER_HOUR_USD else 0.0
    return {
        "amount_paid_usd": round(paid, 2),
        "client_balance_usd": round(client_balance, 2),
        "margin_keini_usd": round(margin_keini, 2),
        "estimated_extra_hours": round(extra_hours, 2),
        "never_expires": True,
        "margin_percent_keini": RECHARGE_MARGIN_KEINI * 100,
    }
