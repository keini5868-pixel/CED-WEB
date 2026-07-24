"""Estrategia 2 — patrón de velas alternadas (experimental).

- Secuencia de colores alternados; velas indecisas/cortas rellenan el color faltante
- Rango fijo = high/low de la primera vela (no acumulado)
- Opera en confirmaciones (2ª y 4ª) mientras el cierre se mantenga en el rango
- Invalidación compartida: cierre fuera del rango fijo
"""

from __future__ import annotations

from app.services.pocket_option.range_invalidation import (
    is_pattern_invalidated,
    range_from_candle,
)
from app.services.pocket_option.types import Candle, FixedRange, Signal

INDECISIVE_BODY_RATIO = 0.22


def _color(candle: Candle) -> str | None:
    if candle.body_ratio <= INDECISIVE_BODY_RATIO or candle.open == candle.close:
        return None
    return "green" if candle.is_bull else "red"


def _sequence_ok(candles: list[Candle]) -> tuple[list[str], FixedRange] | None:
    if not candles:
        return None
    first = candles[0]
    first_color = _color(first)
    if first_color is None:
        # Primera no puede ser solo relleno
        return None
    fixed = range_from_candle(first)
    colors: list[str] = [first_color]
    expected = "red" if first_color == "green" else "green"

    for c in candles[1:]:
        if is_pattern_invalidated(fixed, c):
            return None
        col = _color(c)
        if col is None:
            colors.append(expected)
            expected = "red" if expected == "green" else "green"
            continue
        if col != expected:
            return None
        colors.append(col)
        expected = "red" if col == "green" else "green"
    return colors, fixed


def evaluate_alternating(candles: list[Candle], *, asset: str = "") -> Signal | None:
    if len(candles) < 2:
        return None
    window = candles[-40:] if len(candles) > 40 else candles

    for length in (4, 2):
        if len(window) < length:
            continue
        chunk = window[-length:]
        built = _sequence_ok(chunk)
        if not built:
            continue
        colors, fixed = built
        last = chunk[-1]
        if is_pattern_invalidated(fixed, last):
            continue
        last_color = colors[-1]
        direction = "call" if last_color == "green" else "put"
        level = (fixed.high + fixed.low) / 2.0
        return Signal(
            strategy="alternating",
            direction=direction,  # type: ignore[arg-type]
            level=level,
            reason=(
                f"Alternadas: {''.join(c[0] for c in colors)} "
                f"confirmación #{length}, rango [{fixed.low:.5f},{fixed.high:.5f}]"
            ),
            asset=asset,
        )
    return None
