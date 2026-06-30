"""Métricas de latencia por turno de voz — diagnóstico en logs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VoiceTurnLatency:
    call_id: str
    response_id: int
    transcript_final_ts: float = field(default_factory=time.time)
    debounce_end_ts: float | None = None
    llm_request_ts: float | None = None
    llm_first_token_ts: float | None = None
    first_audio_ts: float | None = None
    path: str = ""

    def mark_debounce_end(self) -> None:
        self.debounce_end_ts = time.time()

    def mark_llm_request(self, *, path: str = "") -> None:
        self.llm_request_ts = time.time()
        if path:
            self.path = path

    def mark_llm_first_token(self) -> None:
        if self.llm_first_token_ts is None:
            self.llm_first_token_ts = time.time()

    def mark_first_audio(self) -> None:
        if self.first_audio_ts is None:
            self.first_audio_ts = time.time()
        self._log_summary()

    def _ms(self, start: float | None, end: float | None) -> int | None:
        if start is None or end is None:
            return None
        return int((end - start) * 1000)

    def _log_summary(self) -> None:
        debounce_ms = self._ms(self.transcript_final_ts, self.debounce_end_ts)
        to_llm_ms = self._ms(self.debounce_end_ts or self.transcript_final_ts, self.llm_request_ts)
        llm_ms = self._ms(self.llm_request_ts, self.llm_first_token_ts)
        audio_ms = self._ms(self.llm_first_token_ts, self.first_audio_ts)
        total_ms = self._ms(self.transcript_final_ts, self.first_audio_ts)
        logger.info(
            "[VOICE:LATENCY] call=%s rid=%s path=%s debounce=%sms to_llm=%sms "
            "llm=%sms to_audio=%sms total=%sms",
            self.call_id[:12],
            self.response_id,
            self.path or "-",
            debounce_ms if debounce_ms is not None else "-",
            to_llm_ms if to_llm_ms is not None else "-",
            llm_ms if llm_ms is not None else "-",
            audio_ms if audio_ms is not None else "-",
            total_ms if total_ms is not None else "-",
        )


_active: dict[tuple[str, int], VoiceTurnLatency] = {}


def start_turn(call_id: str, response_id: int) -> VoiceTurnLatency:
    key = (call_id, response_id)
    turn = VoiceTurnLatency(call_id=call_id, response_id=response_id)
    _active[key] = turn
    if len(_active) > 64:
        oldest = sorted(_active.items(), key=lambda item: item[1].transcript_final_ts)[:8]
        for stale_key, _ in oldest:
            _active.pop(stale_key, None)
    return turn


def get_turn(call_id: str, response_id: int) -> VoiceTurnLatency | None:
    return _active.get((call_id, response_id))
