#!/usr/bin/env python3
"""Bootstrap Retell agent — ejecutar con variables de entorno de Railway."""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import reload_settings
from app.services.retell_agent_cache import set_bootstrapped_agent
from app.services.retell_agent_setup import bootstrap_retell_if_needed


def main() -> None:
    settings = reload_settings()
    missing = []
    if not settings.retell_api_key.strip():
        missing.append("RETELL_API_KEY")
    if not settings.google_api_key.strip():
        missing.append("GOOGLE_API_KEY")
    if missing:
        print("ERROR: faltan variables:", ", ".join(missing))
        sys.exit(1)

    # Producción Retell requiere URL pública HTTPS para WebSocket
    if "localhost" in settings.api_public_url:
        print("AVISO: API_PUBLIC_URL es localhost — use la URL Railway en producción.")

    result = bootstrap_retell_if_needed()
    if not result:
        print("ERROR: bootstrap falló — revise logs")
        sys.exit(1)

    set_bootstrapped_agent(result["agent_id"], result)
    print("OK")
    print(f"RETELL_AGENT_ID={result['agent_id']}")
    print(f"RETELL_VOICE_ID={result['voice_id']}")
    print(f"LLM_WEBSOCKET={result['llm_websocket_url']}")
    print(f"BRAIN={result['brain']}")


if __name__ == "__main__":
    main()
