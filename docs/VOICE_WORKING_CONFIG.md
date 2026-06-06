# Voz CED — configuración validada (no perder)

**Estado:** Validado en local — mayo 2026  
**Fuente de verdad en código:** `apps/web/src/lib/voice/live/voice-profile.lock.ts`

## Stack

| Parámetro | Valor |
|-----------|--------|
| Modelo | `gemini-2.5-flash-native-audio-preview-12-2025` |
| SDK | `@google/genai` · `ai.live.connect` · API `v1alpha` |
| Voz por defecto | **Charon** |
| Playback | `AudioStreamer` (Google live-api-web-console) |
| Captura | `AudioRecorder` + worklet inline 16 kHz |
| Barge-in | `NO_INTERRUPTION` (servidor) |
| Web search | Backend `[CED_BRIEF]` — no `googleSearch` en Live |

## Archivos clave

| Archivo | Rol |
|---------|-----|
| `voice-profile.lock.ts` | Constantes bloqueadas |
| `build-live-config.ts` | Config Gemini Live |
| `ced-live-client.ts` | WebSocket + turnos + tools |
| `audio-streamer.ts` / `audio-recorder.ts` | Audio |
| `useCedVoiceSession.ts` | Orquestación UI |
| `ced_live_voice_prompt.py` | System instruction backend |
| `apps/api/.env` → `GEMINI_LIVE_MODEL` | Modelo en API |

## Preferencias usuario (localStorage)

- `ced_voice_prefs` — idioma, velocidad, voz, paleta
- `ced_mic_enabled` — mic recordado

## Reinicio dev

```powershell
cd CED-WEB
pnpm dev:api
pnpm dev:web
```

Hard refresh en dashboard tras cambios en audio: **Ctrl+Shift+R**.

## Antes de cambiar voz

1. Leer `voice-profile.lock.ts`
2. Probar MIC + 2 preguntas + búsqueda web + sistema avanzado
3. Actualizar `version` en el lock si cambias algo a propósito
