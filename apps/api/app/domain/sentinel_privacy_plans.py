"""Sentinel Privacy — producto aparte de CED (sello ZK / Midnight)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SentinelPlanId(StrEnum):
    SOLO = "sentinel_solo"
    PRO = "sentinel_pro"
    BUSINESS = "sentinel_business"


SENTINEL_PLAN_PRICES_USD: dict[str, int] = {
    SentinelPlanId.SOLO.value: 12,
    SentinelPlanId.PRO.value: 29,
    SentinelPlanId.BUSINESS.value: 79,
}

SENTINEL_SEALS_PER_MONTH: dict[str, int] = {
    SentinelPlanId.SOLO.value: 10,
    SentinelPlanId.PRO.value: 40,
    SentinelPlanId.BUSINESS.value: 150,
}

SENTINEL_PLAN_LABELS: dict[str, str] = {
    SentinelPlanId.SOLO.value: "Sentinel Privacy Solo",
    SentinelPlanId.PRO.value: "Sentinel Privacy Pro",
    SentinelPlanId.BUSINESS.value: "Sentinel Privacy Business",
}

STRIPE_SENTINEL_CHECKOUT_PLANS = frozenset(SENTINEL_PLAN_PRICES_USD.keys())


def is_sentinel_privacy_plan(plan_id: str | None) -> bool:
    pid = (plan_id or "").strip().lower()
    return pid in STRIPE_SENTINEL_CHECKOUT_PLANS


def normalize_sentinel_plan_id(plan_id: str | None) -> str:
    pid = (plan_id or "").strip().lower().replace("-", "_")
    if pid in STRIPE_SENTINEL_CHECKOUT_PLANS:
        return pid
    aliases = {
        "solo": SentinelPlanId.SOLO.value,
        "sentinel_privacy_solo": SentinelPlanId.SOLO.value,
        "pro": SentinelPlanId.PRO.value,
        "business": SentinelPlanId.BUSINESS.value,
    }
    return aliases.get(pid, SentinelPlanId.SOLO.value)


@dataclass(frozen=True)
class SentinelPlanPublic:
    id: str
    label: str
    price_usd: int
    seals_per_month: int
    highlights: tuple[str, ...]


def public_sentinel_plans_catalog() -> list[dict]:
    rows: list[SentinelPlanPublic] = [
        SentinelPlanPublic(
            id=SentinelPlanId.SOLO.value,
            label=SENTINEL_PLAN_LABELS[SentinelPlanId.SOLO.value],
            price_usd=SENTINEL_PLAN_PRICES_USD[SentinelPlanId.SOLO.value],
            seals_per_month=SENTINEL_SEALS_PER_MONTH[SentinelPlanId.SOLO.value],
            highlights=(
                "Sellos verificables (hash + tiempo)",
                "Contenido sensible fuera de la cadena",
                "Ideal para personas y freelancers",
                "Compatible con Lace / Midnight (cuando actives Shield)",
            ),
        ),
        SentinelPlanPublic(
            id=SentinelPlanId.PRO.value,
            label=SENTINEL_PLAN_LABELS[SentinelPlanId.PRO.value],
            price_usd=SENTINEL_PLAN_PRICES_USD[SentinelPlanId.PRO.value],
            seals_per_month=SENTINEL_SEALS_PER_MONTH[SentinelPlanId.PRO.value],
            highlights=(
                "Todo lo de Solo",
                "Más sellos para equipos pequeños",
                "PDFs, acuerdos y entregables de CED",
                "Prioridad en nuevas funciones de privacidad",
            ),
        ),
        SentinelPlanPublic(
            id=SentinelPlanId.BUSINESS.value,
            label=SENTINEL_PLAN_LABELS[SentinelPlanId.BUSINESS.value],
            price_usd=SENTINEL_PLAN_PRICES_USD[SentinelPlanId.BUSINESS.value],
            seals_per_month=SENTINEL_SEALS_PER_MONTH[SentinelPlanId.BUSINESS.value],
            highlights=(
                "Todo lo de Pro",
                "Volumen para negocios y agencias",
                "Soporte para despliegue dedicado (roadmap)",
                "Facturación empresarial vía Stripe",
            ),
        ),
    ]
    return [
        {
            "id": r.id,
            "label": r.label,
            "price_usd": r.price_usd,
            "seals_per_month": r.seals_per_month,
            "highlights": list(r.highlights),
        }
        for r in rows
    ]
