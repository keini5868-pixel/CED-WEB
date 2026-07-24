"""Cliente Pocket Option — BinaryOptionsToolsV2 + validación dura de DEMO."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.pocket_option.candles import normalize_candles
from app.services.pocket_option.types import Candle, Direction

logger = logging.getLogger("ced.pocket_option")


class PocketOptionDemoError(RuntimeError):
    """Se intenta operar sin sesión demo — abortar siempre."""


class PocketOptionClientError(RuntimeError):
    pass


def ssid_explicitly_real(ssid: str) -> bool:
    """True si el SSID declara isDemo:0 (cuenta real)."""
    raw = (ssid or "").strip()
    if not raw:
        return False
    if re.search(r'"isDemo"\s*:\s*0\b', raw):
        return True
    if re.search(r"'isDemo'\s*:\s*0\b", raw):
        return True
    try:
        # Permitir JSON embebido en 42["auth",{...}]
        m = re.search(r"\{.*\}", raw)
        if m:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and data.get("isDemo") in (0, False, "0"):
                return True
    except (json.JSONDecodeError, TypeError):
        pass
    return False


def ssid_claims_demo(ssid: str) -> bool:
    raw = (ssid or "").strip()
    if not raw:
        return False
    if ssid_explicitly_real(raw):
        return False
    if re.search(r'"isDemo"\s*:\s*1\b', raw):
        return True
    if re.search(r"'isDemo'\s*:\s*1\b", raw):
        return True
    try:
        m = re.search(r"\{.*\}", raw)
        if m:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and data.get("isDemo") in (1, True, "1"):
                return True
    except (json.JSONDecodeError, TypeError):
        pass
    # SSID corto sin metadata — exigir is_demo() en runtime
    return True


class PocketOptionClient:
    """Wrapper async con circuit-breaker ligero y guardas demo."""

    def __init__(self, ssid: str) -> None:
        self._ssid = (ssid or "").strip()
        self._api: Any = None
        self._fail_streak = 0
        self.circuit_open = False
        self._circuit_threshold = 5

    @property
    def connected(self) -> bool:
        if self._api is None:
            return False
        try:
            return bool(self._api.is_connected)
        except Exception:  # noqa: BLE001
            return False

    async def connect(self) -> None:
        if not self._ssid:
            raise PocketOptionClientError("POCKET_OPTION_SSID vacío")
        if ssid_explicitly_real(self._ssid):
            raise PocketOptionDemoError(
                "SSID declara isDemo:0 — operativa real PROHIBIDA. Abortando."
            )
        try:
            from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
        except ImportError as exc:
            raise PocketOptionClientError(
                "BinaryOptionsToolsV2 no instalado en el entorno API"
            ) from exc

        self._api = PocketOptionAsync(self._ssid)
        # Dar tiempo a handshake
        import asyncio

        await asyncio.sleep(3)
        await self.require_demo()
        self._fail_streak = 0
        self.circuit_open = False
        logger.info("[PO] conectado (demo verificado)")

    async def require_demo(self) -> None:
        if self._api is None:
            raise PocketOptionClientError("Cliente no conectado")
        if ssid_explicitly_real(self._ssid):
            raise PocketOptionDemoError(
                "SSID declara isDemo:0 — operativa real PROHIBIDA."
            )
        try:
            is_demo = bool(self._api.is_demo())
        except Exception as exc:  # noqa: BLE001
            raise PocketOptionClientError(
                f"No se pudo verificar is_demo(): {exc}"
            ) from exc
        if not is_demo:
            raise PocketOptionDemoError(
                "Sesión NO es demo (is_demo=False). Abortando — nunca operar real."
            )

    async def disconnect(self) -> None:
        if self._api is None:
            return
        try:
            await self._api.disconnect()
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._api.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self._api = None

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.connect()

    def _note_failure(self) -> None:
        self._fail_streak += 1
        if self._fail_streak >= self._circuit_threshold:
            self.circuit_open = True
            logger.error(
                "[PO] circuit-breaker ABIERTO tras %s fallos", self._fail_streak
            )

    def _note_success(self) -> None:
        self._fail_streak = 0
        self.circuit_open = False

    async def balance(self) -> float:
        await self.require_demo()
        assert self._api is not None
        try:
            bal = float(await self._api.balance())
            self._note_success()
            return bal
        except Exception as exc:  # noqa: BLE001
            self._note_failure()
            raise PocketOptionClientError(str(exc)) from exc

    async def fetch_candles(
        self, asset: str, *, period: int = 60, history_seconds: int = 7200
    ) -> list[Candle]:
        await self.require_demo()
        assert self._api is not None
        try:
            raw = await self._api.get_candles(asset, period, history_seconds)
            candles = normalize_candles(raw if isinstance(raw, list) else [])
            self._note_success()
            return candles
        except Exception as exc:  # noqa: BLE001
            self._note_failure()
            raise PocketOptionClientError(str(exc)) from exc

    async def place(
        self,
        *,
        asset: str,
        direction: Direction,
        amount: float,
        expiry_seconds: int,
    ) -> tuple[str, dict[str, Any]]:
        """Coloca orden solo tras re-verificar demo."""
        if self.circuit_open:
            raise PocketOptionClientError("Circuit-breaker abierto — sin órdenes")
        await self.require_demo()
        assert self._api is not None
        try:
            if direction == "call":
                trade_id, deal = await self._api.buy(
                    asset, float(amount), int(expiry_seconds)
                )
            else:
                trade_id, deal = await self._api.sell(
                    asset, float(amount), int(expiry_seconds)
                )
            self._note_success()
            return str(trade_id), deal if isinstance(deal, dict) else {"deal": deal}
        except PocketOptionDemoError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._note_failure()
            raise PocketOptionClientError(str(exc)) from exc

    async def check_win(self, trade_id: str) -> str:
        await self.require_demo()
        assert self._api is not None
        result = await self._api.check_win(trade_id)
        if isinstance(result, dict):
            return str(result.get("result") or result.get("status") or "pending")
        return str(result or "pending")
