"""Modelos Gemini Live recomendados (AI Studio / Developer API)."""

from __future__ import annotations

# Recomendación Fase 2B (documentación Google, mar 2026):
# - gemini-2.5-flash-native-audio-preview-12-2025: último native audio preview (multimodal, español, VAD)
# - gemini-2.0-flash-live-001 y gemini-2.5-flash-preview-native-audio-dialog: APAGADOS / deprecados
# - gemini-3.1-flash-live-preview: sucesor anunciado; usar cuando esté en tu cuenta

RECOMMENDED_LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

FALLBACK_LIVE_MODELS = [
    "gemini-2.5-flash-native-audio-preview-09-2025",
    "gemini-2.5-flash-native-audio-preview-12-2025",
]

DEPRECATED_LIVE_MODELS = frozenset(
    {
        "gemini-2.0-flash-live-001",
        "gemini-2.5-flash-preview-native-audio-dialog",
        "gemini-live-2.5-flash-preview",
    }
)
