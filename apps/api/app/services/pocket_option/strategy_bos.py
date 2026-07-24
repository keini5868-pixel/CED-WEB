"""Estrategia 1 — Break of Structure / price action (prioridad).

- Swings automáticos sobre últimas ~100 velas de 1m
- Mínimo 2 escalones confirmados antes de entrada en el 3ro
- Nivel = precio exacto del último swing
- Confirmación: cuerpo cierra del lado correcto; cuerpo corto/mediano;
  preferible retest sin ruptura
- Invalidación: cierre del lado contrario al nivel (rango fijo alrededor del nivel)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.pocket_option.range_invalidation import (
    is_pattern_invalidated,
    make_fixed_range,
)
from app.services.pocket_option.types import Candle, Direction, FixedRange, Signal

# Cuerpo grande: body_ratio > este umbral → descartar confirmación
MAX_BODY_RATIO = 0.72
# Lookback para swings locales
SWING_LEFT = 2
SWING_RIGHT = 2
# Tolerancia del rango fijo alrededor del nivel (fracción del ATR local)
LEVEL_BAND_ATR = 0.15


@dataclass
class _Swing:
    index: int
    price: float
    kind: str  # "high" | "low"


def _atr(candles: list[Candle], n: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    window = candles[-n:] if len(candles) >= n else candles
    trs: list[float] = []
    for i, c in enumerate(window):
        if i == 0:
            trs.append(c.range)
            continue
        prev = window[i - 1]
        trs.append(
            max(
                c.high - c.low,
                abs(c.high - prev.close),
                abs(c.low - prev.close),
            )
        )
    return sum(trs) / len(trs) if trs else 0.0


def detect_swings(candles: list[Candle]) -> list[_Swing]:
    swings: list[_Swing] = []
    n = len(candles)
    for i in range(SWING_LEFT, n - SWING_RIGHT):
        hi = candles[i].high
        lo = candles[i].low
        is_high = all(
            hi >= candles[j].high
            for j in range(i - SWING_LEFT, i + SWING_RIGHT + 1)
            if j != i
        )
        is_low = all(
            lo <= candles[j].low
            for j in range(i - SWING_LEFT, i + SWING_RIGHT + 1)
            if j != i
        )
        if is_high:
            swings.append(_Swing(index=i, price=hi, kind="high"))
        elif is_low:
            swings.append(_Swing(index=i, price=lo, kind="low"))
    return swings


def _count_bullish_steps(lows: list[_Swing]) -> int:
    """Escalones alcistas: cada low respeta el low anterior (no lo rompe)."""
    if len(lows) < 2:
        return 0
    steps = 0
    for i in range(1, len(lows)):
        if lows[i].price >= lows[i - 1].price:
            steps += 1
        else:
            steps = 0
    return steps


def _count_bearish_steps(highs: list[_Swing]) -> int:
    if len(highs) < 2:
        return 0
    steps = 0
    for i in range(1, len(highs)):
        if highs[i].price <= highs[i - 1].price:
            steps += 1
        else:
            steps = 0
    return steps


def _body_ok(candle: Candle) -> bool:
    return 0.0 < candle.body_ratio <= MAX_BODY_RATIO


def _level_band(level: float, atr: float) -> FixedRange:
    pad = max(atr * LEVEL_BAND_ATR, abs(level) * 1e-5)
    return make_fixed_range(level + pad, level - pad)


def evaluate_bos(candles: list[Candle], *, asset: str = "") -> Signal | None:
    if len(candles) < 30:
        return None
    window = candles[-100:] if len(candles) > 100 else candles
    swings = detect_swings(window)
    if len(swings) < 3:
        return None

    lows = [s for s in swings if s.kind == "low"]
    highs = [s for s in swings if s.kind == "high"]
    atr = _atr(window)
    last = window[-1]

    # Canal alcista → call en retest del último swing low
    bull_steps = _count_bullish_steps(lows)
    if bull_steps >= 2 and lows:
        level = lows[-1].price
        band = _level_band(level, atr)
        if is_pattern_invalidated(band, last) and last.close < level:
            return None
        # Confirmación: cierre por encima del nivel, cuerpo corto/mediano
        if last.close > level and _body_ok(last):
            # Retest: low tocó o se acercó al nivel en esta o previas 2 velas
            retest = any(
                c.low <= level + max(atr * 0.05, 1e-6)
                for c in window[-3:]
            )
            if retest or last.open <= level:
                return Signal(
                    strategy="bos",
                    direction="call",
                    level=level,
                    reason=(
                        f"BOS alcista: {bull_steps} escalones, "
                        f"cierre>{level:.5f}, cuerpo OK"
                        + (" + retest" if retest else "")
                    ),
                    asset=asset,
                )

    # Canal bajista → put en retest del último swing high
    bear_steps = _count_bearish_steps(highs)
    if bear_steps >= 2 and highs:
        level = highs[-1].price
        band = _level_band(level, atr)
        if is_pattern_invalidated(band, last) and last.close > level:
            return None
        if last.close < level and _body_ok(last):
            retest = any(
                c.high >= level - max(atr * 0.05, 1e-6)
                for c in window[-3:]
            )
            if retest or last.open >= level:
                return Signal(
                    strategy="bos",
                    direction="put",
                    level=level,
                    reason=(
                        f"BOS bajista: {bear_steps} escalones, "
                        f"cierre<{level:.5f}, cuerpo OK"
                        + (" + retest" if retest else "")
                    ),
                    asset=asset,
                )

    return None


def direction_side_ok(direction: Direction, candle: Candle, level: float) -> bool:
    if direction == "call":
        return candle.close > level
    return candle.close < level
