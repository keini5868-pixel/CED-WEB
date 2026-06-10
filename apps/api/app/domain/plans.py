"""Planes CED — suscripciones + recargas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlanId(StrEnum):
    STARTER = "starter"
    PRO = "pro"
    ELITE = "elite"
    FOUNDING = "founding"
    FREE_BASIC = "free_basic"
    # Legacy (compat)
    ELITE_FOUNDING = "elite_founding"
    ELITE_REGULAR = "elite_regular"


FOUNDING_MEMBER_MAX_SLOTS = 50
TRIAL_DAYS = 7
TRIAL_VOICE_MINUTES_PER_DAY = 15
USAGE_WARNING_PERCENT = 80

# Costo referencia voz OpenAI Realtime Mini (~$0.20/min sesión activa)
OPENAI_VOICE_COST_PER_HOUR_USD = 12.0
# Legacy alias recargas
GEMINI_COST_PER_HOUR_USD = OPENAI_VOICE_COST_PER_HOUR_USD
RECHARGE_MARGIN_KEINI = 0.40
RECHARGE_CLIENT_SHARE = 0.60
RECHARGE_MIN_USD = 10
RECHARGE_MAX_USD = 500
RECHARGE_QUICK_AMOUNTS_USD = (10, 20, 40, 50, 100)

# Minutos diarios Founding (cap margen)
FOUNDING_VOICE_CAP_MINUTES = 90

PLAN_PRICES_USD: dict[str, int] = {
    PlanId.STARTER.value: 30,
    PlanId.PRO.value: 59,
    PlanId.ELITE.value: 99,
    PlanId.FOUNDING.value: 149,
    PlanId.FREE_BASIC.value: 0,
    PlanId.ELITE_FOUNDING.value: 149,
    PlanId.ELITE_REGULAR.value: 99,
}

STRIPE_CHECKOUT_PLANS = frozenset(
    {
        PlanId.STARTER.value,
        PlanId.PRO.value,
        PlanId.ELITE.value,
        PlanId.FOUNDING.value,
    }
)


@dataclass(frozen=True)
class PlanLimits:
    voice_minutes_per_day: int
    web_searches_per_day: int  # -1 = ilimitado
    ai_images_standard_per_month: int
    ai_images_hd_per_month: int
    voice_enabled: bool
    camera_enabled: bool
    meta_social_enabled: bool
    prospection_enabled: bool
    pdf_reports: bool
    claude_messages_per_day: int  # -1 = ilimitado

    @property
    def gemini_minutes_per_day(self) -> int:
        return self.voice_minutes_per_day

    @property
    def ai_images_per_month(self) -> int:
        std = self.ai_images_standard_per_month
        hd = self.ai_images_hd_per_month
        if std < 0 or hd < 0:
            return -1
        return std + hd


PLAN_LIMITS: dict[str, PlanLimits] = {
    PlanId.STARTER.value: PlanLimits(
        voice_minutes_per_day=15,
        web_searches_per_day=30,
        ai_images_standard_per_month=3,
        ai_images_hd_per_month=0,
        voice_enabled=True,
        camera_enabled=False,
        meta_social_enabled=False,
        prospection_enabled=False,
        pdf_reports=False,
        claude_messages_per_day=-1,
    ),
    PlanId.PRO.value: PlanLimits(
        voice_minutes_per_day=30,
        web_searches_per_day=-1,
        ai_images_standard_per_month=10,
        ai_images_hd_per_month=3,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=False,
        prospection_enabled=False,
        pdf_reports=False,
        claude_messages_per_day=-1,
    ),
    PlanId.ELITE.value: PlanLimits(
        voice_minutes_per_day=60,
        web_searches_per_day=-1,
        ai_images_standard_per_month=20,
        ai_images_hd_per_month=8,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=True,
        prospection_enabled=True,
        pdf_reports=True,
        claude_messages_per_day=-1,
    ),
    PlanId.FOUNDING.value: PlanLimits(
        voice_minutes_per_day=FOUNDING_VOICE_CAP_MINUTES,
        web_searches_per_day=-1,
        ai_images_standard_per_month=40,
        ai_images_hd_per_month=15,
        voice_enabled=True,
        camera_enabled=True,
        meta_social_enabled=True,
        prospection_enabled=True,
        pdf_reports=True,
        claude_messages_per_day=-1,
    ),
    PlanId.FREE_BASIC.value: PlanLimits(
        voice_minutes_per_day=0,
        web_searches_per_day=0,
        ai_images_standard_per_month=0,
        ai_images_hd_per_month=0,
        voice_enabled=False,
        camera_enabled=False,
        meta_social_enabled=False,
        prospection_enabled=False,
        pdf_reports=False,
        claude_messages_per_day=50,
    ),
}

PLAN_LIMITS[PlanId.ELITE_FOUNDING.value] = PLAN_LIMITS[PlanId.FOUNDING.value]
PLAN_LIMITS[PlanId.ELITE_REGULAR.value] = PLAN_LIMITS[PlanId.ELITE.value]

PLAN_LABELS: dict[str, str] = {
    PlanId.STARTER.value: "CED Starter",
    PlanId.PRO.value: "CED Pro",
    PlanId.ELITE.value: "CED Élite",
    PlanId.FOUNDING.value: "CED Founding",
    PlanId.FREE_BASIC.value: "CED Básico Gratis",
    PlanId.ELITE_FOUNDING.value: "CED Founding",
    PlanId.ELITE_REGULAR.value: "CED Élite",
}


def normalize_plan_id(plan_id: str | None) -> str:
    pid = (plan_id or PlanId.FREE_BASIC.value).strip()
    if pid == PlanId.ELITE_FOUNDING.value:
        return PlanId.FOUNDING.value
    if pid == PlanId.ELITE_REGULAR.value:
        return PlanId.ELITE.value
    if pid in PLAN_LIMITS:
        return pid
    return PlanId.FREE_BASIC.value


def get_plan_limits(plan_id: str | None) -> PlanLimits:
    return PLAN_LIMITS[normalize_plan_id(plan_id)]


def plan_minutes_daily(plan_id: str | None) -> int:
    return get_plan_limits(plan_id).voice_minutes_per_day


# Alias legacy
CED_ELITE = get_plan_limits(PlanId.ELITE.value)


def recharge_balance_to_bonus_minutes(balance_usd: float) -> float:
    if balance_usd <= 0:
        return 0.0
    client_share = balance_usd * RECHARGE_CLIENT_SHARE
    hours = client_share / GEMINI_COST_PER_HOUR_USD if GEMINI_COST_PER_HOUR_USD else 0.0
    return round(hours * 60, 2)


def quote_recharge(amount_usd: float) -> dict[str, float | bool]:
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


def public_plans_catalog() -> list[dict]:
    order = (PlanId.STARTER, PlanId.PRO, PlanId.ELITE, PlanId.FOUNDING)
    out: list[dict] = []
    for pid in order:
        limits = PLAN_LIMITS[pid.value]
        out.append(
            {
                "id": pid.value,
                "label": PLAN_LABELS[pid.value],
                "price_usd": PLAN_PRICES_USD[pid.value],
                "minutes_per_day": limits.voice_minutes_per_day,
                "web_searches_per_day": limits.web_searches_per_day,
                "ai_images_standard_per_month": limits.ai_images_standard_per_month,
                "ai_images_hd_per_month": limits.ai_images_hd_per_month,
                "voice_enabled": limits.voice_enabled,
                "camera_enabled": limits.camera_enabled,
                "meta_social_enabled": limits.meta_social_enabled,
                "prospection_enabled": limits.prospection_enabled,
            }
        )
    return out
