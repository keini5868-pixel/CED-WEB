"""Normalización de velas desde BinaryOptionsToolsV2 / dicts genéricos."""

from __future__ import annotations

from typing import Any

from app.services.pocket_option.types import Candle


def normalize_candles(raw: list[dict[str, Any]] | None) -> list[Candle]:
    out: list[Candle] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        try:
            t = item.get("time") or item.get("timestamp") or item.get("t") or 0
            o = float(item.get("open", item.get("o")))
            h = float(item.get("high", item.get("h")))
            low = float(item.get("low", item.get("l")))
            c = float(item.get("close", item.get("c")))
        except (TypeError, ValueError):
            continue
        try:
            ts = int(float(t))
        except (TypeError, ValueError):
            ts = 0
        if h < low:
            h, low = low, h
        out.append(Candle(time=ts, open=o, high=h, low=low, close=c))
    out.sort(key=lambda x: x.time)
    return out


def last_n(candles: list[Candle], n: int) -> list[Candle]:
    if n <= 0:
        return []
    return candles[-n:]
