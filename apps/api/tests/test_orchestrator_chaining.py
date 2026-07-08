"""Test de encadenamiento end-to-end del orquestador v2 (Fase 3).

Escenario pedido por el usuario:
  1) "llévame a Charlotte"                        → activa Maps
  2) "¿cuál es la mejor ruta?" (cotidiana)        → fluye, Maps sigue activo
  3) "cuando llegue, hazme un PDF de finanzas"    → cambia a PDF, cierra Maps

Además: un módulo colgado se cancela por timeout, cierra y vuelve a neutral
(bug "se queda pegado esperando indefinidamente").

No usa red ni I/O: los módulos son falsos y el clasificador LLM se fuerza a
"nunca acción" (las frases de prueba usan anclas estrictas, no lo necesitan).
"""

from __future__ import annotations

import asyncio

import pytest

from app.services import ced_orchestrator as orch_mod
from app.services.ced_orchestrator import CedOrchestrator
from app.services.module_detector import detect_intent as _real_detect_intent
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance


class FakeModule:
    """Módulo de prueba: registra llamadas y responde de forma determinista."""

    def __init__(self, name: str, *, handles: bool = True, sleep: float = 0.0) -> None:
        self.name = name
        self._handles = handles
        self._sleep = sleep
        self._state: dict = {}
        self.activated = 0
        self.commands = 0
        self.deactivated = 0

    async def activate(self, transcript, *, user_id, call_id, user_text="", utterances=None):
        self.activated += 1
        if self._sleep:
            await asyncio.sleep(self._sleep)
        return ModuleResult(
            ok=True,
            spoken=f"[{self.name}] activado",
            handles_response=True,
        )

    async def handle_command(self, transcript, *, user_id, call_id, user_text="", utterances=None):
        self.commands += 1
        if self._sleep:
            await asyncio.sleep(self._sleep)
        return ModuleResult(
            ok=True,
            spoken=f"[{self.name}] {transcript}",
            handles_response=self._handles,
        )

    async def deactivate(self, *, user_id, call_id):
        self.deactivated += 1
        self._state = {}

    def get_state(self):
        return dict(self._state)

    def is_active(self):
        return True


def _install_fakes(monkeypatch, fakes: dict[str, FakeModule]) -> None:
    monkeypatch.setattr(orch_mod, "build_module", lambda name: fakes[name])
    # Memoria modular: sin DB.
    monkeypatch.setattr(orch_mod, "load_module_memory", lambda name, uid: None)
    # Clasificador de Etapa 2 forzado a "nunca acción" (evita cualquier red).
    monkeypatch.setattr(
        orch_mod,
        "_detect_intent_v2",
        lambda text, **kw: _real_detect_intent(text, classify=lambda t, m: False),
    )


def test_full_chaining_maps_then_casual_then_pdf(monkeypatch):
    # Maps NO maneja preguntas casuales → caen a conversación (chat base fluye).
    map_mod = FakeModule("map", handles=False)
    pdf_mod = FakeModule("pdf", handles=True)
    fakes = {"map": map_mod, "pdf": pdf_mod}
    _install_fakes(monkeypatch, fakes)

    orch = CedOrchestrator(call_id="chain-1")
    uid = "user-chain-1"
    transcript: list[Utterance] = []

    async def run():
        snaps: dict[str, object] = {}
        # --- Turno 1: activa Maps ---
        transcript.append(Utterance(role="user", content="llévame a Charlotte"))
        snaps["r1"] = await orch.process(
            user_text="llévame a Charlotte",
            transcript=transcript,
            call_id="chain-1",
            user_id=uid,
        )
        snaps["active_after_t1"] = orch.active_module

        # --- Turno 2: pregunta cotidiana durante Maps ---
        transcript.append(Utterance(role="user", content="¿cuál es la mejor ruta?"))
        snaps["r2"] = await orch.process(
            user_text="¿cuál es la mejor ruta?",
            transcript=transcript,
            call_id="chain-1",
            user_id=uid,
        )
        snaps["active_after_t2"] = orch.active_module

        # --- Turno 3: cambia a PDF de finanzas ---
        transcript.append(
            Utterance(role="user", content="cuando llegue, hazme un PDF de análisis de finanzas")
        )
        snaps["r3"] = await orch.process(
            user_text="cuando llegue, hazme un PDF de análisis de finanzas",
            transcript=transcript,
            call_id="chain-1",
            user_id=uid,
        )
        snaps["active_after_t3"] = orch.active_module
        return snaps

    s = asyncio.run(run())

    # Turno 1 — Maps activado y activo.
    assert s["r1"].module_activated == "map"
    assert s["active_after_t1"] == "map"
    assert map_mod.activated == 1

    # Turno 2 — Maps sigue activo, la conversación fluye, sin bloqueo.
    assert map_mod.commands >= 1  # handle_active corrió (chat base respondió)
    assert s["active_after_t2"] == "map"
    assert s["r2"].conversation_continues is True

    # Turno 3 — cambio limpio a PDF: Maps cerrado, PDF activado y completado
    # (PDF es efímero → tras entregar vuelve a conversación neutral).
    assert s["r3"].module_activated == "pdf"
    assert map_mod.deactivated == 1
    assert pdf_mod.activated == 1
    assert s["active_after_t3"] is None  # volvió a neutral, sin estado residual


def test_hung_module_times_out_and_returns_neutral(monkeypatch):
    # Módulo que se cuelga en activate → debe cancelarse y volver a neutral.
    hung = FakeModule("finance", sleep=5.0)
    fakes = {"finance": hung}
    _install_fakes(monkeypatch, fakes)
    monkeypatch.setattr(orch_mod, "MODULE_CALL_TIMEOUT_SEC", 0.2)

    orch = CedOrchestrator(call_id="chain-hang")
    uid = "user-hang"

    async def run():
        return await orch.process(
            user_text="cómo van mis finanzas",
            transcript=[Utterance(role="user", content="cómo van mis finanzas")],
            call_id="chain-hang",
            user_id=uid,
        )

    result = asyncio.run(run())

    # No se queda pegado: responde con error y cierra el módulo → neutral.
    assert result.handles_response is True
    assert "tardó demasiado" in (result.spoken or "").lower()
    assert orch.active_module is None


if __name__ == "__main__":  # ejecución directa para prueba manual
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
