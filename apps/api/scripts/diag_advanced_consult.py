"""Prueba real consult_advanced — 3 complejidades (simple/media/compleja)."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

# load .env
for line in Path(__file__).resolve().parents[1].joinpath(".env").read_text(
    encoding="utf-8", errors="ignore"
).splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from app.services import voice_client_session as vcs  # noqa: E402
from app.services.advanced_mode_flow import activate_advanced_mode  # noqa: E402
from app.services.retell_native_pilot import (  # noqa: E402
    execute_activate_advanced_mode_tool,
    execute_consult_advanced_tool,
)

USER = "diag-advanced-consult-user"

QUESTIONS = [
    ("simple", "Qué es la fotosíntesis en dos oraciones."),
    (
        "media",
        "Compara brevemente interés simple e interés compuesto con un ejemplo de mil dólares.",
    ),
    (
        "compleja",
        "Quiero hacer un análisis de lo que es la filosofía de Sócrates y qué tiene que ver "
        "eso, o si tiene algo relevante o igual a la idea del alquimista, comparando con el "
        "libro El Alquimista.",
    ),
]


async def main() -> None:
    vcs.set_advanced_mode_active(USER, False)
    act = await execute_activate_advanced_mode_tool(
        user_id=USER,
        payload={"call": {"call_id": "diag-adv"}},
        args={},
    )
    print("ACTIVATE:", act["ok"], act["result"][:120].replace("\n", " | "))
    assert act["ok"]
    assert vcs.is_advanced_mode_active(USER)

    for label, q in QUESTIONS:
        started = time.perf_counter()
        out = await execute_consult_advanced_tool(
            user_id=USER,
            payload={
                "call": {
                    "call_id": "diag-adv",
                    "transcript_object": [{"role": "user", "content": q}],
                }
            },
            args={"query": q},
        )
        elapsed = time.perf_counter() - started
        result = out["result"]
        print(f"\n=== {label.upper()} ({elapsed:.1f}s) ok={out['ok']} len={len(result)} ===")
        print(result[:500])
        assert out["ok"], f"{label} failed: {result}"
        assert "[meta:" not in result
        assert len(result) >= 40, f"{label} too short"
        assert elapsed < 45, f"{label} exceeded 45s: {elapsed}"

    print("\nALL_THREE_OK")


if __name__ == "__main__":
    asyncio.run(main())
