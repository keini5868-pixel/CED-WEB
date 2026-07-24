"""Worker async — espaciado de operaciones + evaluación de estrategias.

No corre en el request HTTP del panel. Arranca desde lifespan si el kill-switch está ON.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.services.pocket_option.client import (
    PocketOptionClient,
    PocketOptionClientError,
    PocketOptionDemoError,
)
from app.services.pocket_option import store
from app.services.pocket_option.strategy_alternating import evaluate_alternating
from app.services.pocket_option.strategy_bos import evaluate_bos
from app.services.pocket_option.types import Signal, TradeRecord

logger = logging.getLogger("ced.pocket_option.worker")

_task: asyncio.Task[None] | None = None
_stop = asyncio.Event()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _evaluate_signal(client: PocketOptionClient, asset: str) -> Signal | None:
    settings = get_settings()
    candles = await client.fetch_candles(asset, period=60, history_seconds=7200)
    # Prioridad: BOS
    if settings.pocket_option_strategy_bos_enabled:
        sig = evaluate_bos(candles, asset=asset)
        if sig:
            return sig
    if settings.pocket_option_strategy_alt_enabled:
        return evaluate_alternating(candles, asset=asset)
    return None


async def _run_loop() -> None:
    settings = get_settings()
    asset = settings.pocket_option_asset.strip() or "EURUSD_otc"
    interval = max(60, int(settings.pocket_option_interval_seconds))
    amount = float(settings.pocket_option_amount)
    expiry = int(settings.pocket_option_expiry_seconds)

    store.update_status(
        running=True,
        asset=asset,
        interval_seconds=interval,
        strategy_bos_enabled=settings.pocket_option_strategy_bos_enabled,
        strategy_alt_enabled=settings.pocket_option_strategy_alt_enabled,
        last_error=None,
    )

    client = PocketOptionClient(settings.pocket_option_ssid)
    try:
        await client.connect()
        bal = await client.balance()
        store.update_status(
            connected=True,
            is_demo=True,
            balance=bal,
            circuit_open=False,
        )
    except (PocketOptionDemoError, PocketOptionClientError) as exc:
        logger.error("[PO-WORKER] no se pudo iniciar: %s", exc)
        store.update_status(
            running=False,
            connected=False,
            last_error=str(exc),
            is_demo=False if isinstance(exc, PocketOptionDemoError) else None,
        )
        return

    next_slot = _utc_now()
    store.update_status(next_slot_at=_iso(next_slot))

    while not _stop.is_set():
        settings = get_settings()
        if not settings.pocket_option_module_enabled:
            logger.info("[PO-WORKER] kill-switch OFF — deteniendo")
            break

        now = _utc_now()
        if now < next_slot:
            wait = min(15.0, (next_slot - now).total_seconds())
            try:
                await asyncio.wait_for(_stop.wait(), timeout=max(0.5, wait))
                break
            except asyncio.TimeoutError:
                continue

        store.update_status(
            strategy_bos_enabled=settings.pocket_option_strategy_bos_enabled,
            strategy_alt_enabled=settings.pocket_option_strategy_alt_enabled,
            interval_seconds=max(60, int(settings.pocket_option_interval_seconds)),
            circuit_open=client.circuit_open,
        )

        if client.circuit_open:
            logger.warning("[PO-WORKER] circuit abierto — reconectando…")
            try:
                await client.reconnect()
                store.update_status(
                    connected=True,
                    is_demo=True,
                    circuit_open=False,
                    last_error=None,
                )
            except Exception as exc:  # noqa: BLE001
                store.update_status(
                    connected=False,
                    last_error=str(exc),
                    circuit_open=True,
                )
                next_slot = _utc_now() + timedelta(seconds=interval)
                store.update_status(next_slot_at=_iso(next_slot))
                continue

        try:
            await client.require_demo()
            signal = await _evaluate_signal(client, asset)
            bal = await client.balance()
            store.update_status(balance=bal, connected=True, last_error=None)

            if signal is None:
                logger.info("[PO-WORKER] sin señal — siguiente slot en %ss", interval)
            else:
                trade_id = ""
                record = TradeRecord(
                    id=str(uuid.uuid4())[:12],
                    ts=_iso(_utc_now()),
                    strategy=signal.strategy,
                    direction=signal.direction,
                    asset=asset,
                    amount=amount,
                    expiry_seconds=expiry,
                    level=signal.level,
                    reason=signal.reason,
                    result="pending",
                )
                try:
                    trade_id, _deal = await client.place(
                        asset=asset,
                        direction=signal.direction,
                        amount=amount,
                        expiry_seconds=expiry,
                    )
                    record.id = trade_id or record.id
                    store.append_trade(record)
                    # Esperar resultado del expiry
                    await asyncio.sleep(expiry + 2)
                    try:
                        outcome = await client.check_win(record.id)
                        outcome_l = outcome.lower()
                        if "win" in outcome_l:
                            record.result = "win"
                        elif "loss" in outcome_l or "lose" in outcome_l:
                            record.result = "loss"
                        elif "draw" in outcome_l or "equal" in outcome_l:
                            record.result = "draw"
                        else:
                            record.result = "pending"
                        store.update_trade(record.id, result=record.result)
                    except Exception as exc:  # noqa: BLE001
                        store.update_trade(
                            record.id, result="error", error=str(exc)
                        )
                    bal = await client.balance()
                    store.update_status(balance=bal)
                    logger.info(
                        "[PO-WORKER] trade %s %s %s → %s",
                        record.id,
                        signal.strategy,
                        signal.direction,
                        record.result,
                    )
                except PocketOptionDemoError as exc:
                    record.result = "error"
                    record.error = str(exc)
                    store.append_trade(record)
                    store.update_status(last_error=str(exc), is_demo=False)
                    logger.error("[PO-WORKER] DEMO GUARD: %s — deteniendo worker", exc)
                    break
                except Exception as exc:  # noqa: BLE001
                    record.result = "error"
                    record.error = str(exc)
                    store.append_trade(record)
                    store.update_status(last_error=str(exc))
                    logger.exception("[PO-WORKER] error al operar")

        except PocketOptionDemoError as exc:
            store.update_status(last_error=str(exc), is_demo=False, connected=False)
            logger.error("[PO-WORKER] DEMO GUARD: %s — deteniendo", exc)
            break
        except Exception as exc:  # noqa: BLE001
            store.update_status(last_error=str(exc), circuit_open=client.circuit_open)
            logger.exception("[PO-WORKER] ciclo falló")

        interval = max(60, int(get_settings().pocket_option_interval_seconds))
        next_slot = _utc_now() + timedelta(seconds=interval)
        store.update_status(next_slot_at=_iso(next_slot))

    try:
        await client.disconnect()
    except Exception:  # noqa: BLE001
        pass
    store.update_status(running=False, connected=False)
    logger.info("[PO-WORKER] detenido")


def start_worker_if_enabled() -> asyncio.Task[None] | None:
    """Llamar desde lifespan (async)."""
    global _task
    settings = get_settings()
    if not settings.pocket_option_module_enabled:
        logger.info("[PO-WORKER] desactivado (POCKET_OPTION_MODULE_ENABLED=false)")
        return None
    if not settings.pocket_option_ssid.strip():
        logger.warning("[PO-WORKER] enabled pero POCKET_OPTION_SSID vacío")
        store.update_status(
            running=False,
            last_error="POCKET_OPTION_SSID vacío",
        )
        return None
    if _task and not _task.done():
        return _task
    _stop.clear()
    _task = asyncio.create_task(_run_loop(), name="pocket-option-worker")
    return _task


async def stop_worker() -> None:
    global _task
    _stop.set()
    if _task and not _task.done():
        try:
            await asyncio.wait_for(_task, timeout=10)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            _task.cancel()
    _task = None
    store.update_status(running=False)
