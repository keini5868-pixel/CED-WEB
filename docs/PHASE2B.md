# Fase 2B — Audio/video Gemini Live completo

## Modelo recomendado (configurado)

**`gemini-2.5-flash-native-audio-preview-12-2025`**

| Criterio | Decisión |
|----------|----------|
| Voz natural en español | Native audio (no TTS encadenado) |
| Latencia | Flash + Live API con VAD (~sub-500 ms típico en red buena) |
| Audio + video | Soportado vía `sendRealtimeInput` |
| Producción | Preview activa en AI Studio (dic 2025); sucesor estable: `gemini-live-2.5-flash-native-audio` en Vertex |
| Precio | Flash tier; audio in/out facturado por minuto en Live API |

**Deprecados (no usar):**
- `gemini-2.0-flash-live-001` — apagado dic 2025
- `gemini-2.5-flash-preview-native-audio-dialog` — apagado

**Variable:** `GEMINI_LIVE_MODEL=gemini-2.5-flash-native-audio-preview-12-2025` en `apps/api/.env`

## Entregables 2B

1. Mic → PCM 16 kHz → `sendRealtimeInput` en bucle (~250 ms)
2. Reproducción audio respuesta (cola PCM 24 kHz)
3. Frames JPEG cámara cada 2 s al Live API
4. `usage_logs` + tick cada 15 s → barra USAGE en vivo
5. `voice_conversations` + `voice_messages` en Supabase

## Migración SQL

Ejecutar en Supabase (o script):

`apps/api/migrations/003_voice_conversations.sql`

## Probar

**Primera vez (dependencias Python):**

```powershell
pnpm setup:api
```

Luego:

```powershell
pnpm dev:api
pnpm dev:web
```

1. Login → `/dashboard`
2. MIC → hablar → escuchar respuesta de CED
3. CAM → “mira esto” o botón cámara
4. Barra USAGE sube tras ~15 s de sesión
5. HIST → ver conversaciones guardadas

## Micrófono no activa — checklist

1. API corriendo: `pnpm dev:api` → `http://localhost:8000/v1/integrations` → `gemini.ok: true`
2. Abrir dashboard en **http://localhost:3000** (no IP LAN sin HTTPS)
3. Clic **MIC** → permitir micrófono en el navegador
4. Estado: `Activando micrófono…` → `Conectando con CED…` → `Escuchándote…`
5. Si falla: leer mensaje rojo bajo el orbe (permiso, API caída, token, límite)

## Estado pipeline voz (Fase 2B)

| Paso | ¿Implementado? | Notas |
|------|----------------|-------|
| Mic → PCM 16 kHz | Sí | `pcmCapture.ts` |
| → `sendRealtimeInput` | Sí | `{ data, mimeType: "audio/pcm;rate=16000" }` |
| ← audio modelo | Sí | `useGeminiLive` → `onAudio` |
| Reproducción altavoz | Sí | `pcmPlayback.ts` — **bloqueado si MUTE (rojo)** |
| Cámara → Gemini | Sí | JPEG cada ~2 s |
| USAGE tick / barra | Sí | Requiere `pnpm dev:api` |
| Historial Supabase | Sí | Tras transcripciones |

**El backend NO recibe PCM** — el audio va **directo del navegador a Gemini** (token efímero). La API solo emite el token y registra minutos.

### Debug en consola (F12)

```js
localStorage.setItem('CED_DEBUG_VOICE', '1')
```

Recarga, MIC, habla: verás `[CED voice] audio chunk` si Gemini responde.

## Validar

- [ ] Token efímero OK (`GOOGLE_API_KEY` en API)
- [ ] Audio bidireccional
- [ ] Cámara envía frames
- [ ] Uso en barra actualiza
- [ ] Mensajes en historial tras hablar

## Fase 3 (siguiente)

**Inicio del carrusel 3D izquierdo:** solo tras confirmación de validación 2B en local.

- Spec completa: [PHASE3_LEFT_CAROUSEL.md](./PHASE3_LEFT_CAROUSEL.md)
- Orden: MVP visual mock → APIs una por una (Tavily, health, Meta, leads, etc.)
- Function calling real (search_web, memory, etc.)
- Redis para sesiones + rate limit
- Continuar conversación desde historial
