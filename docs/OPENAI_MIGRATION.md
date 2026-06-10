# Migración OpenAI Realtime — CED-WEB

## Resumen

Migración completa de voz **Gemini Live → OpenAI Realtime** con límites duros en servidor.

## Cambios principales

- **Voz:** `gpt-4o-mini-realtime-preview` (fallback `gpt-4o-realtime-preview`)
- **Voz default:** `alloy`, PCM16 24 kHz
- **Tools:** 12 herramientas vía OpenAI Realtime + backend CED
- **Análisis profundo:** Claude (`consultar_claude`)
- **Búsqueda web:** Tavily (`search_web`)
- **Imágenes:** GPT-Image-1 con límites std/HD por plan

## Límites diarios de voz (servidor)

| Plan | Min/día |
|------|---------|
| Trial 7d | 15 |
| Free Basic | 0 |
| Starter $30 | 15 |
| Pro $59 | 30 |
| Élite $99 | 60 |
| Founding $149 | 90 |

Verificación: antes de `/v1/openai/realtime/session` y cada 30s en `/v1/usage/session/tick`.

Avisos: 80% warn, 95% critical, 100% corte + modal recarga.

## Variables Railway (CED-WEB)

```
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL_VOICE=gpt-4o-mini-realtime-preview
OPENAI_MODEL_IMAGE=gpt-image-1
OPENAI_DEFAULT_VOICE=alloy
COST_TRACKING_ENABLED=true
```

Keini solo debe agregar `OPENAI_API_KEY` y saldo en platform.openai.com.

## SQL

Ejecutar en Supabase: `apps/api/migrations/011_openai_migration.sql`

## Archivos clave

- Backend: `apps/api/app/services/openai_realtime.py`, `openai_voice_tools.py`
- Router: `apps/api/app/routers/openai.py`
- Frontend: `apps/web/src/lib/voice/live/ced-live-client.ts` (OpenAI WS)
- Hook: `apps/web/src/hooks/useCedVoiceSession.ts`

## Eliminado

- `gemini_live.py`, `gemini.py` router, `gemini_models.py`, `gemini_voices.py`, `gemini_deep_analysis.py`

`gemini_grounded.py` se mantiene como motor Tavily/brief (sin dependencia de voz Gemini).
