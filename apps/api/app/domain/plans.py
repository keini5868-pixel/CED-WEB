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

# Costo unitario de recarga (monedero multi-recurso) — aprobado Keini 2026-07
VOICE_COST_PER_MIN_USD = 0.10
IMAGE_STD_COST_USD = 0.02
IMAGE_HD_COST_USD = 0.04
WEB_SEARCH_COST_USD = 0.01
PDF_COST_USD = 0.05
VISION_COST_USD = 0.03
ADVANCED_TURN_COST_USD = 0.05
MAPS_ROUTE_COST_USD = 0.02

# Alias: 1 h voz = 60 * $0.10
OPENAI_VOICE_COST_PER_HOUR_USD = VOICE_COST_PER_MIN_USD * 60.0
GEMINI_COST_PER_HOUR_USD = OPENAI_VOICE_COST_PER_HOUR_USD
RECHARGE_MARGIN_KEINI = 0.40
RECHARGE_CLIENT_SHARE = 0.60
RECHARGE_MIN_USD = 10
RECHARGE_MAX_USD = 500
RECHARGE_QUICK_AMOUNTS_USD = (10, 20, 40, 50, 100)

RESOURCE_UNIT_COSTS_USD: dict[str, float] = {
    "voice_min": VOICE_COST_PER_MIN_USD,
    "image_std": IMAGE_STD_COST_USD,
    "image_hd": IMAGE_HD_COST_USD,
    "web_search": WEB_SEARCH_COST_USD,
    "pdf": PDF_COST_USD,
    "vision": VISION_COST_USD,
    "advanced_turn": ADVANCED_TURN_COST_USD,
    "maps_route": MAPS_ROUTE_COST_USD,
}

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
    ai_images_standard_per_day: int
    ai_images_hd_per_day: int
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
        std = self.ai_images_standard_per_day
        hd = self.ai_images_hd_per_day
        if std < 0 or hd < 0:
            return -1
        return std + hd

    # Alias legacy (antes era mensual; ahora la cuota real es diaria)
    @property
    def ai_images_standard_per_month(self) -> int:
        return self.ai_images_standard_per_day

    @property
    def ai_images_hd_per_month(self) -> int:
        return self.ai_images_hd_per_day


PLAN_LIMITS: dict[str, PlanLimits] = {
    PlanId.STARTER.value: PlanLimits(
        voice_minutes_per_day=15,
        web_searches_per_day=30,
        ai_images_standard_per_day=20,
        ai_images_hd_per_day=0,
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
        ai_images_standard_per_day=45,
        ai_images_hd_per_day=5,
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
        ai_images_standard_per_day=95,
        ai_images_hd_per_day=15,
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
        ai_images_standard_per_day=145,
        ai_images_hd_per_day=25,
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
        ai_images_standard_per_day=0,
        ai_images_hd_per_day=0,
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
    """Minutos de voz equivalentes al monedero (balance ya es crédito neto 60%)."""
    if balance_usd <= 0 or VOICE_COST_PER_MIN_USD <= 0:
        return 0.0
    return round(float(balance_usd) / VOICE_COST_PER_MIN_USD, 2)


def quote_recharge(amount_usd: float) -> dict[str, float | bool | int]:
    paid = max(RECHARGE_MIN_USD, min(RECHARGE_MAX_USD, float(amount_usd)))
    client_balance = paid * RECHARGE_CLIENT_SHARE
    margin_keini = paid * RECHARGE_MARGIN_KEINI
    voice_mins = (
        client_balance / VOICE_COST_PER_MIN_USD if VOICE_COST_PER_MIN_USD else 0.0
    )
    extra_hours = voice_mins / 60.0
    return {
        "amount_paid_usd": round(paid, 2),
        "client_balance_usd": round(client_balance, 2),
        "margin_keini_usd": round(margin_keini, 2),
        "estimated_extra_hours": round(extra_hours, 2),
        "estimated_voice_minutes": int(voice_mins),
        "estimated_images_std": int(
            client_balance / IMAGE_STD_COST_USD if IMAGE_STD_COST_USD else 0
        ),
        "estimated_images_hd": int(
            client_balance / IMAGE_HD_COST_USD if IMAGE_HD_COST_USD else 0
        ),
        "estimated_web_searches": int(
            client_balance / WEB_SEARCH_COST_USD if WEB_SEARCH_COST_USD else 0
        ),
        "estimated_pdfs": int(client_balance / PDF_COST_USD if PDF_COST_USD else 0),
        "never_expires": True,
        "margin_percent_keini": RECHARGE_MARGIN_KEINI * 100,
        "voice_cost_per_min_usd": VOICE_COST_PER_MIN_USD,
    }


def unit_cost_usd(resource: str) -> float:
    return float(RESOURCE_UNIT_COSTS_USD.get(resource) or 0.0)


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
                "ai_images_standard_per_day": limits.ai_images_standard_per_day,
                "ai_images_hd_per_day": limits.ai_images_hd_per_day,
                "voice_enabled": limits.voice_enabled,
                "camera_enabled": limits.camera_enabled,
                "meta_social_enabled": limits.meta_social_enabled,
                "prospection_enabled": limits.prospection_enabled,
            }
        )
    return out
