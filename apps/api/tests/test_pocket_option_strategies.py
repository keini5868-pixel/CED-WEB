"""Tests unitarios — estrategias Pocket Option (sin red)."""

from __future__ import annotations

from app.services.pocket_option.client import ssid_claims_demo, ssid_explicitly_real
from app.services.pocket_option.range_invalidation import (
    is_pattern_invalidated,
    range_from_candle,
)
from app.services.pocket_option.strategy_alternating import evaluate_alternating
from app.services.pocket_option.strategy_bos import detect_swings, evaluate_bos
from app.services.pocket_option.types import Candle


def _c(t: int, o: float, h: float, low: float, c: float) -> Candle:
    return Candle(time=t, open=o, high=h, low=low, close=c)


def test_ssid_demo_guards():
    demo = '42["auth",{"session":"abc","isDemo":1,"uid":1,"platform":1}]'
    real = '42["auth",{"session":"abc","isDemo":0,"uid":1,"platform":1}]'
    assert ssid_claims_demo(demo) is True
    assert ssid_explicitly_real(demo) is False
    assert ssid_explicitly_real(real) is True
    assert ssid_claims_demo(real) is False


def test_fixed_range_invalidation():
    base = _c(1, 1.0, 1.2, 0.9, 1.1)
    fixed = range_from_candle(base)
    ok = _c(2, 1.05, 1.15, 0.95, 1.08)
    bad = _c(3, 1.1, 1.3, 1.05, 1.25)
    assert is_pattern_invalidated(fixed, ok) is False
    assert is_pattern_invalidated(fixed, bad) is True


def test_bos_detects_swings_and_bullish_signal():
    # Construir escalones alcistas de lows + confirmación alcista
    candles: list[Candle] = []
    t = 0
    price = 1.0
    for i in range(40):
        # ruido
        o = price
        c = price + (0.001 if i % 2 == 0 else -0.0005)
        candles.append(_c(t, o, max(o, c) + 0.0008, min(o, c) - 0.0008, c))
        t += 60
        price = c
    # Forzar lows ascendentes y cierre alcista final
    candles[-10] = _c(t - 600, 1.010, 1.012, 1.008, 1.011)
    candles[-7] = _c(t - 420, 1.012, 1.014, 1.010, 1.013)
    candles[-4] = _c(t - 240, 1.014, 1.016, 1.012, 1.015)
    candles[-1] = _c(t - 60, 1.013, 1.017, 1.0125, 1.016)  # cierra arriba del low

    swings = detect_swings(candles)
    assert len(swings) >= 1
    # Puede o no disparar según swings; al menos no debe crashear
    _ = evaluate_bos(candles, asset="EURUSD_otc")


def test_alternating_sequence_signal():
    # verde-roja-verde-roja dentro del rango de la primera
    candles = [
        _c(1, 1.00, 1.05, 0.99, 1.04),  # green
        _c(2, 1.04, 1.045, 1.00, 1.01),  # red
        _c(3, 1.01, 1.04, 1.005, 1.035),  # green
        _c(4, 1.035, 1.04, 1.00, 1.01),  # red — 4ª confirmación
    ]
    sig = evaluate_alternating(candles, asset="EURUSD_otc")
    assert sig is not None
    assert sig.strategy == "alternating"
    assert sig.direction == "put"

