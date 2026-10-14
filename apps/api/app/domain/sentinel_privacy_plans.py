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
    SentinelPlanId.BUSINESS.value: 200,
}

SENTINEL_SEALS_PER_MONTH: dict[str, int] = {
    SentinelPlanId.SOLO.value: 10,
    SentinelPlanId.PRO.value: 40,
    SentinelPlanId.BUSINESS.value: 200,
}

SENTINEL_PLAN_LABELS: dict[str, str] = {
    SentinelPlanId.SOLO.value: "Sentinel Privacy Solo",
    SentinelPlanId.PRO.value: "Sentinel Privacy Pro",
    SentinelPlanId.BUSINESS.value: "Sentinel Privacy",
}

STRIPE_SENTINEL_CHECKOUT_PLANS = frozenset(SENTINEL_PLAN_PRICES_USD.keys())

# Oferta pública principal (SKU aparte de CED Élite/Founding).
SENTINEL_PUBLIC_FLAGSHIP_ID = SentinelPlanId.BUSINESS.value

SENTINEL_PRODUCT_SPEC = (
    "Sellos verificables: solo hash SHA-256 + marca de tiempo en cadena (Midnight/Lace).",
    "El PDF, audio o acuerdo NO se sube a la blockchain ni a servidores públicos.",
    "Facturación Stripe separada: no sustituye ni mezcla tu plan CED (voz, chat, imágenes).",
    "Requiere wallet Lace en red Midnight para anclar el sello (demo en /shield).",
    "Ideal para contratos, entregables sensibles y cumplimiento sin exponer contenido.",
)


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
    """Catálogo público: un SKU flagship aparte de CED."""
    pid = SENTINEL_PUBLIC_FLAGSHIP_ID
    row = SentinelPlanPublic(
        id=pid,
        label=SENTINEL_PLAN_LABELS[pid],
        price_usd=SENTINEL_PLAN_PRICES_USD[pid],
        seals_per_month=SENTINEL_SEALS_PER_MONTH[pid],
        highlights=SENTINEL_PRODUCT_SPEC,
    )
    return [
        {
            "id": row.id,
            "label": row.label,
            "price_usd": row.price_usd,
            "seals_per_month": row.seals_per_month,
            "highlights": list(row.highlights),
            "product_line": "sentinel_privacy",
            "not_ced_plan": True,
            "ced_plans_unrelated": True,
        }
    ]


def all_sentinel_checkout_plans_catalog() -> list[dict]:
    """Todos los SKUs Stripe (admin / legacy)."""
    rows: list[SentinelPlanPublic] = [
        SentinelPlanPublic(
            id=SentinelPlanId.SOLO.value,
            label=SENTINEL_PLAN_LABELS[SentinelPlanId.SOLO.value],
            price_usd=SENTINEL_PLAN_PRICES_USD[SentinelPlanId.SOLO.value],
            seals_per_month=SENTINEL_SEALS_PER_MONTH[SentinelPlanId.SOLO.value],
            highlights=SENTINEL_PRODUCT_SPEC[:3],
        ),
        SentinelPlanPublic(
            id=SentinelPlanId.PRO.value,
            label=SENTINEL_PLAN_LABELS[SentinelPlanId.PRO.value],
            price_usd=SENTINEL_PLAN_PRICES_USD[SentinelPlanId.PRO.value],
            seals_per_month=SENTINEL_SEALS_PER_MONTH[SentinelPlanId.PRO.value],
            highlights=SENTINEL_PRODUCT_SPEC[:4],
        ),
        SentinelPlanPublic(
            id=SentinelPlanId.BUSINESS.value,
            label=SENTINEL_PLAN_LABELS[SentinelPlanId.BUSINESS.value],
            price_usd=SENTINEL_PLAN_PRICES_USD[SentinelPlanId.BUSINESS.value],
            seals_per_month=SENTINEL_SEALS_PER_MONTH[SentinelPlanId.BUSINESS.value],
            highlights=SENTINEL_PRODUCT_SPEC,
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
