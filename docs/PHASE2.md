# Fase 2 — Cerebro, voz y orbe JARVIS

## Entregado en esta iteración

### Orbe central (Three.js + R3F)
- `JarvisOrbScene.tsx` — anillos 3D, partículas, núcleo emisivo
- Estados: `idle`, `listening`, `processing`, `speaking`, `error`, `paused`
- Reactividad a `audioLevel` (Web Audio API)
- Paletas: cyan, gold, matrix, iron

### Controles de voz
- Mic, cámara, mute, pausa, stop (modal), historial (panel), configuración, archivos (stub)
- `localStorage` para mic y preferencias

### Gemini Live
- `POST /v1/gemini/ephemeral-token` (JWT Supabase, sin API key en web)
- Cliente `@google/genai` live.connect v1alpha
- Prompt sistema en `apps/api/app/domain/ced_system_prompt.py`

### Cámara por voz
- `parseCameraIntent()` — español
- Auto-off cámara tras 5 min sin uso

## Requisitos

```env
# apps/api/.env
GOOGLE_API_KEY=tu_clave
GEMINI_LIVE_MODEL=gemini-2.5-flash-preview-native-audio-dialog
```

```powershell
cd CED-WEB
npx pnpm@9.15.0 install
pip install -r apps/api/requirements.txt
pnpm dev:web
pnpm dev:api
```

## Probar

1. Login → `/dashboard`
2. Clic **MIC** → permiso micrófono → orbe `listening`
3. Si falla token: revisar `GOOGLE_API_KEY` y logs API
4. `/dev/hud-preview` — vista sin auth (solo dev)

## Siguiente (Fase 2b)

- Streaming PCM mic → Gemini en tiempo real
- Envío frames de cámara al modelo
- Persistencia historial en Supabase
- Barra USAGE en vivo desde API
