"""Economía del módulo Video Edit — tokens por duración real.

Confirmado Keini 2026-08:
  $1 = 100 tokens
  1 segundo de salida = 1 token
  Mínimo facturable = 30 segundos
  Margen neto objetivo 30–35% sobre COGS (~$0.007/s → venta $0.01/s)
  Soft cap = 2 renders/día
"""

from __future__ import annotations

import math
from typing import Any

# Conversión
TOKENS_PER_USD = 100
USD_PER_TOKEN = 0.01
TOKENS_PER_SECOND = 1
MIN_BILLABLE_SECONDS = 30

# Soft cap anti-quema
VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY = 2

# COGS planificación (stack económico)
PROVIDER_COGS_PER_SECOND_USD = 0.0070
CLIENT_PRICE_PER_SECOND_USD = USD_PER_TOKEN * TOKENS_PER_SECOND  # 0.01

# Packs Stripe (1:1 — sin recorte 60/40 del monedero general)
VIDEO_EDIT_TOKEN_PACKS_USD: tuple[int, ...] = (10, 20, 50)

# Veo Lite — criterio estricto
VEO_MAX_SECONDS = 4
VEO_MAX_PER_JOB = 1
VEO_MAX_RATIO = 0.10  # ≤1 Veo cada 10 videos


def tokens_for_duration_seconds(duration_sec: float | int) -> int:
    """Tokens a cobrar por segundos reales de salida (ceil, mín. 30)."""
    seconds = max(0.0, float(duration_sec))
    billable = max(MIN_BILLABLE_SECONDS, math.ceil(seconds))
    return int(billable * TOKENS_PER_SECOND)


def usd_for_tokens(tokens: int) -> float:
    return round(max(0, int(tokens)) * USD_PER_TOKEN, 2)


def tokens_for_usd(amount_usd: float) -> int:
    """Crédito 1:1 — $1 = 100 tokens."""
    paid = max(0.0, float(amount_usd))
    return int(round(paid * TOKENS_PER_USD))


def quote_video_edit_pack(amount_usd: float) -> dict[str, Any]:
    paid = float(amount_usd)
    if int(round(paid)) not in VIDEO_EDIT_TOKEN_PACKS_USD:
        # Permitir solo packs oficiales; redondear al más cercano válido si hace falta
        paid = float(min(VIDEO_EDIT_TOKEN_PACKS_USD, key=lambda x: abs(x - paid)))
    tokens = tokens_for_usd(paid)
    return {
        "amount_paid_usd": round(paid, 2),
        "tokens": tokens,
        "tokens_per_usd": TOKENS_PER_USD,
        "seconds_equivalent": tokens,  # 1 token = 1 s
        "base_videos_30s": tokens // MIN_BILLABLE_SECONDS,
        "never_expires": True,
        "margin_note": "Margen 30–35% embebido en $0.01/s vs COGS $0.007/s",
    }


def quote_render(duration_sec: float | int) -> dict[str, Any]:
    tokens = tokens_for_duration_seconds(duration_sec)
    cogs = round(float(duration_sec) * PROVIDER_COGS_PER_SECOND_USD, 4)
    # COGS del mínimo facturable si output < 30s
    billable_sec = max(MIN_BILLABLE_SECONDS, math.ceil(float(duration_sec)))
    cogs_billable = round(billable_sec * PROVIDER_COGS_PER_SECOND_USD, 4)
    price = usd_for_tokens(tokens)
    margin_usd = round(price - cogs_billable, 4)
    margin_pct = round((margin_usd / price) * 100, 1) if price > 0 else 0.0
    return {
        "duration_sec": round(float(duration_sec), 2),
        "billable_seconds": billable_sec,
        "tokens": tokens,
        "price_usd": price,
        "cogs_usd": cogs_billable,
        "margin_usd": margin_usd,
        "margin_percent": margin_pct,
        "min_billable_seconds": MIN_BILLABLE_SECONDS,
    }


def video_edit_pack_catalog() -> list[dict[str, Any]]:
    return [quote_video_edit_pack(amount) for amount in VIDEO_EDIT_TOKEN_PACKS_USD]
