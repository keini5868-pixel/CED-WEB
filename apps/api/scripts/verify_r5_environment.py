"""Verificación rápida capa 3 environment standalone (r5)."""
from __future__ import annotations

import os

from app.config import get_settings

os.environ["VOICE_TEST_MODE"] = "gemini_standalone"
os.environ["VOICE_STANDALONE_MODULES"] = "environment"
get_settings.cache_clear()

from app.modules.environment_module import is_environment_action_request
from app.services.voice_test_mode import resolve_standalone_forced_module

CASES = [
    ("dame informacion sobre el clima hoy", True),
    ("calidad de aire", True),
    ("Hace calor", False),
    ("hablamos del clima ayer", False),
]

print("resolve_standalone_forced_module")
for phrase, should in CASES:
    mod = resolve_standalone_forced_module(phrase, [], call_id="t", user_id="u")
    env = mod == "environment"
    status = "OK" if env == should else "FAIL"
    print(f"  {status} {phrase!r} -> {mod!r}")

print("is_environment_action_request")
for phrase, should in CASES:
    got = is_environment_action_request(phrase)
    status = "OK" if got == should else "FAIL"
    print(f"  {status} {phrase!r} -> {got}")
