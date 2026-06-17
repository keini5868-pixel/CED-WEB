#!/usr/bin/env python3
"""Crea o actualiza agente Retell CED Jarvis. Uso: python scripts/setup_retell_agent.py"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import reload_settings
from app.services.retell_agent_setup import ensure_retell_agent


def main() -> None:
    settings = reload_settings()
    if not settings.retell_api_key.strip():
        print("ERROR: configure RETELL_API_KEY en apps/api/.env o Railway")
        sys.exit(1)

    agent_id = settings.retell_agent_id.strip() or None
    llm_id = settings.retell_llm_id.strip() or None
    result = ensure_retell_agent(agent_id=agent_id, llm_id=llm_id)
    print("Retell bootstrap OK")
    print(f"  RETELL_LLM_ID={result['llm_id']}")
    print(f"  RETELL_AGENT_ID={result['agent_id']}")
    print(f"  RETELL_VOICE_ID={result['voice_id']}")
    print("\nAgregue estas variables en Railway (servicio API) y redeploy.")


if __name__ == "__main__":
    main()
