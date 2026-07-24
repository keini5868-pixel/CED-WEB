"""Estado en memoria del worker (solo admin lee vía API)."""

from __future__ import annotations

import threading
from copy import deepcopy

from app.services.pocket_option.types import TradeRecord, WorkerStatus

_lock = threading.Lock()
_status = WorkerStatus()


def get_status() -> WorkerStatus:
    with _lock:
        return deepcopy(_status)


def update_status(**kwargs: object) -> None:
    with _lock:
        for key, value in kwargs.items():
            if hasattr(_status, key):
                setattr(_status, key, value)


def append_trade(trade: TradeRecord) -> None:
    with _lock:
        _status.trades.append(trade)
        if len(_status.trades) > 200:
            _status.trades = _status.trades[-200:]


def update_trade(trade_id: str, **kwargs: object) -> None:
    with _lock:
        for t in reversed(_status.trades):
            if t.id == trade_id:
                for key, value in kwargs.items():
                    if hasattr(t, key):
                        setattr(t, key, value)
                break
