# Fase 2B — Refactor voz (may 2026)

Refactor completo del pipeline Gemini Live. Sin parches incrementales.

## Archivos modificados / creados

### Backend
- `apps/api/app/domain/gemini_voices.py` — 30 voces válidas + normalización
- `apps/api/app/domain/ced_live_voice_prompt.py` — persona → rules → guardrails
- `apps/api/app/services/gemini_live.py` — token con `voiceName`
- `apps/api/app/routers/gemini.py` — POST body `voiceName`, GET `/voices`

### Frontend — audio
- `apps/web/public/audio/pcm-capture-processor.js` — AudioWorklet, chunks **30 ms**
- `apps/web/src/lib/audio/pcmCapture.ts` — worklet + fallback
- `apps/web/src/lib/audio/pcmPlayback.ts` — streaming inmediato, métricas play

### Frontend — sesión / UI
- `apps/web/src/hooks/useGeminiLive.ts` — config oficial, sesión única, guards
- `apps/web/src/hooks/useCedVoiceSession.ts` — `applyVoiceChange`, anti-race
- `apps/web/src/lib/voice/geminiVoices.ts` — catálogo UI
- `apps/web/src/lib/voice/voiceTelemetry.ts` — E2E / red / playback
- `apps/web/src/lib/voice/preferences.ts` — `voiceName` (migra `voiceTone`)
- `apps/web/src/components/voice/CedVoiceModals.tsx` — grid voces + APLICAR VOZ
- `apps/web/src/components/voice/CedVoiceDebugPanel.tsx` — panel dev
- `apps/web/src/components/orb/CedOrbOverlay.tsx` — chispas solo cliente
- `packages/types/src/index.ts` — `voiceName` en prefs

## Diagnóstico por bug

| Bug | Causa | Fix |
|-----|-------|-----|
| Latencia alta | Chunks 50–100 ms, cola playback larga | Chunks 30 ms, lookahead ≤ 40 ms |
| Respuestas incoherentes | Prompt bienvenida + turnos mezclados | Prompt nuevo + `TURN_INCLUDES_ONLY_ACTIVITY` |
| No escucha bien | Downsampling irregular | AudioContext 16 kHz + AudioWorklet |
| Voz no cambia | `Aoede` hardcodeada en connect | `voiceName` en token + `applyVoiceChange` |
| Hydration | Math.random / SSR en overlay | Chispas en `useEffect` solo cliente |

## Config Gemini Live (cliente)

- Modelo: `gemini-2.5-flash-native-audio-preview-12-2025`
- `responseModalities: [AUDIO]`
- Sin `languageCode` (native audio multilingüe)
- VAD: `silenceDurationMs: 500`, sensibilidad HIGH
- `START_OF_ACTIVITY_INTERRUPTS` + flush local
- `contextWindowCompression` sliding 12800 tokens
- `enableAffectiveDialog: true`

## Métricas (panel debug)

- **E2E**: fin de habla → primer audio audible (objetivo < 1500 ms)
- **Red**: fin de habla → primer chunk WS
- **Play**: primer chunk → primer sample audible

Visible en dev o `localStorage.CED_DEBUG_VOICE = '1'`.

## Probar

```powershell
pnpm dev:api
pnpm dev:web
```

http://localhost:3000/dashboard

1. MIC ON — silencio hasta que hablas
2. Pregunta corta — revisa E2E en panel
3. CFG → elige Charon → **APLICAR VOZ** (con MIC on)
4. Interrumpe hablando encima

## Limitaciones

- `gemini-3.1-flash-live` no verificado en esta cuenta API
- Latencia depende de red + región Google
- Previews MP3 de voces no incluidos (UI lista nombres)
- Supabase `user_preferences.voice_name` futuro — hoy `localStorage`
