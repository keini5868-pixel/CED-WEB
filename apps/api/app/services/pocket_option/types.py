"""Tipos compartidos del módulo Pocket Option."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Direction = Literal["call", "put"]
StrategyId = Literal["bos", "alternating"]
TradeResult = Literal["win", "loss", "draw", "pending", "error", "skipped"]


@dataclass(frozen=True)
class Candle:
    time: int  # unix seconds
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(0.0, self.high - self.low)

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.close < self.open

    @property
    def body_ratio(self) -> float:
        """Cuerpo / rango (0–1). Velas grandes ~ cerca de 1."""
        r = self.range
        if r <= 0:
            return 0.0
        return self.body / r


@dataclass(frozen=True)
class FixedRange:
    """Rango fijo de invalidación compartido por ambas estrategias."""

    high: float
    low: float

    def contains_close(self, close: float) -> bool:
        return self.low <= close <= self.high

    def invalidated_by(self, candle: Candle) -> bool:
        return not self.contains_close(candle.close)


@dataclass(frozen=True)
class Signal:
    strategy: StrategyId
    direction: Direction
    level: float
    reason: str
    asset: str = ""


@dataclass
class TradeRecord:
    id: str
    ts: str
    strategy: StrategyId
    direction: Direction
    asset: str
    amount: float
    expiry_seconds: int
    level: float
    reason: str
    result: TradeResult = "pending"
    profit: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerStatus:
    running: bool = False
    connected: bool = False
    is_demo: bool | None = None
    balance: float | None = None
    asset: str = ""
    next_slot_at: str | None = None
    last_error: str | None = None
    circuit_open: bool = False
    strategy_bos_enabled: bool = True
    strategy_alt_enabled: bool = False
    interval_seconds: int = 300
    trades: list[TradeRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "connected": self.connected,
            "is_demo": self.is_demo,
            "balance": self.balance,
            "asset": self.asset,
            "next_slot_at": self.next_slot_at,
            "last_error": self.last_error,
            "circuit_open": self.circuit_open,
            "strategy_bos_enabled": self.strategy_bos_enabled,
            "strategy_alt_enabled": self.strategy_alt_enabled,
            "interval_seconds": self.interval_seconds,
            "trades": [t.to_dict() for t in self.trades[-50:]],
        }
