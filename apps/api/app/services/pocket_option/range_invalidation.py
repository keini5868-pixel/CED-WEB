"""Invalidación por rango fijo — compartida por Estrategia 1 y 2."""

from __future__ import annotations

from app.services.pocket_option.types import Candle, FixedRange


def make_fixed_range(high: float, low: float) -> FixedRange:
    if high < low:
        high, low = low, high
    return FixedRange(high=high, low=low)


def range_from_candle(candle: Candle) -> FixedRange:
    return make_fixed_range(candle.high, candle.low)


def is_pattern_invalidated(fixed: FixedRange, candle: Candle) -> bool:
    """True si el cierre de la vela rompe el rango fijo (invalidación)."""
    return fixed.invalidated_by(candle)
