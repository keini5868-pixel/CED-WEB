# Piloto Retell LLM nativo — reporte comparativo

Agente **separado** de producción. Producción (`RETELL_AGENT_ID`, Custom LLM r7) no se modifica.

**Build piloto actual:** `retell-native-pilot-v2b-calendar-oauth-fix`  
**Fase:** clima validado + lectura calendario/Gmail (fix OAuth calendario)

---

## Fix v2b — Calendario OAuth refresh (2026-07-13)

**Síntoma:** `list_calendar_events` fallaba con mensaje genérico mientras Gmail funcionaba en la misma sesión.

**Causa raíz:** Gmail usa `_gmail_api_call()` con **refresh automático** ante 401/403; el módulo calendario llamaba `get_valid_access_token()` una sola vez sin reintentar — token expirado → HTTP 401 → excepción genérica.

**Corrección:**
- `_calendar_api_call()` — mismo patrón que Gmail
- Consultas combinadas **hoy + mañana** en una sola pregunta
- Fallback `resolve_call_user()` si metadata falta en payload Retell
- Logging HTTP en gateway nativo

**No era:** bug de Custom Function ni user_id distinto (Gmail en la misma llamada confirma metadata correcta).

---

## Reporte comparativo — prueba de voz (Fase clima)

Resultado de la prueba profunda del usuario (build `retell-native-pilot-environment-v1`).

### Configuración

| | Producción (r7) | Piloto nativo |
|--|-----------------|---------------|
| Engine | `custom-llm` WebSocket | `retell-llm` |
| Modelo LLM | Gemini 2.5 Flash (API key Google) | Gemini 3.0 Flash (Retell) |
| Voz | Jarvis (`RETELL_VOICE_ID`) | Misma voz (copiada del agente prod) |
| Tool clima | Orquestador + anchors/heurísticas + locks | `get_environment` Custom Function |
| Turnos | Debounce, superseded, answered_key (artesanal) | Gestionado por Retell |

### Resultado cualitativo (confirmado por usuario)

| Criterio | Prod r7 | Piloto nativo |
|----------|---------|---------------|
| Velocidad de respuesta conversacional | Buena con parches | **Excelente** — responde antes de terminar de hablar |
| Ejecución clima con contexto | Funcional tras r3–r7 | **Correcta**, buen contexto conversacional |
| Solapamiento de audio | Historial de bugs (r2–r6) | **Ninguno** (confirmado en audio real) |
| Arrastre / repetición no solicitada | r5 silencio, r6–r7 re-clima | **Ninguno** (confirmado en audio real) |
| Charla casual post-clima | Parcheada en r6–r7 | **Correcta** |
| Silencio durante búsqueda clima | Fillers vía router custom | Pausa audible — **corregido en v2** con `execution_message_type: static_text` |
| Transcripción duplicada en pantalla | Bug cosmético conocido | Igual (cosmético, no afecta audio) — pendiente final |

### Latencia gateway `get_environment` (ms)

Las métricas se registran en memoria en `GET /v1/retell/native-pilot/metrics` (requiere auth).

| Métrica | Prod r7 (Custom LLM) | Piloto nativo |
|---------|----------------------|---------------|
| Turno conversacional (percepción) | Normal | **Muy rápido** |
| Búsqueda clima (web grounding) | ~4–12 s típico + filler router | ~4–12 s (misma capa `handle_environment_query_sync`) |
| Timeout máximo tool | 22 s | 22 s |
| Pausa en silencio pre-respuesta | Filler inconsistente | **v1:** silencio — **v2:** filler estático *"Un momento, consultando el clima, señor."* |

Nota: la latencia de datos ambientales es la misma en ambos sistemas (mismo `EnvironmentModule` + Gemini grounded search). La diferencia está en **coordinación de turnos** y **time-to-first-byte conversacional**, donde Retell nativo gana claramente.

### Bugs de turnos (protocolo r2–r7)

| Bug | Prod r7 | Piloto nativo |
|-----|---------|---------------|
| Solapamiento de audio | Corregido parcialmente | **No observado** |
| Arrastre de turno anterior | Corregido parcialmente | **No observado** |
| Repetición clima no solicitada | r6–r7 parcheado | **No observado** |
| Silencio post-clima (ignorar ack) | r5 parcheado | **No observado** |
| Anchor gaps ("calidad de aire" sin "del") | Parcheado con heurísticas | LLM decide tool — **sin anchor manual** |

### Charla casual

| Frase | Prod r7 | Piloto nativo |
|-------|---------|---------------|
| "Ok, gracias" | OK tras r6–r7 | **OK** |
| "¿Estás ahí?" / "Sí, me escuchas" | OK tras r7 | **OK** |
| Desahogo personal | OK (Gemini) | **OK** (mismo prompt base standalone) |

### Costo por minuto (estimado)

| Componente | Prod r7 | Piloto nativo |
|------------|---------|---------------|
| LLM | Gemini 2.5 Flash vía API Google (~$0.075/1M input, ~$0.30/1M output*) + tokens conversación | Retell factura Gemini 3.0 Flash ~**$0.027/min** (voz incluida en minuto Retell) |
| STT/TTS | Incluido en Retell | Incluido en Retell |
| Infra turnos | Railway API + WebSocket Custom LLM (~1700 LOC) | Incluido en plataforma Retell |
| Búsqueda clima | Google grounding (misma en ambos) | Google grounding (misma en ambos) |

\* Precios Google orientativos; el costo real prod depende de tokens/turno en Custom LLM.

**Observación:** el piloto simplifica la stack (menos compute propio en turnos). El costo Retell por minuto es predecible; prod mezcla Retell + Gemini directo + infra custom.

### Recomendación

- [x] **Proceder a Fase 3** (tools de lectura: calendario, Gmail) — piloto clima estable
- [x] **Migración confirmada** por el usuario
- [ ] Cutover producción — pendiente paridad completa + canary

---

## Fase 3 — tools de lectura (v2)

Nuevas Custom Functions en el mismo agente staging:

| Tool | Tipo | Gateway | Filler durante ejecución |
|------|------|---------|--------------------------|
| `get_environment` | Lectura | `/v1/retell/tools/get_environment` | "Un momento, consultando el clima, señor." |
| `list_calendar_events` | Solo lectura | `/v1/retell/tools/list_calendar_events` | "Un momento, revisando su calendario, señor." |
| `read_gmail` | Solo lectura | `/v1/retell/tools/read_gmail` | "Un momento, revisando su correo, señor." |

**Regla de diseño:** escritura (agendar, enviar correo, registrar finanzas, publicar) requerirá tools separadas + estado de confirmación — no incluidas en v2.

Si el usuario pide agendar o enviar correo, el backend responde que esa acción llegará con confirmación en fase posterior.

---

## Operación

### Variables Railway (piloto)

```env
RETELL_NATIVE_STAGING_AGENT_ID=
RETELL_NATIVE_STAGING_LLM_ID=
RETELL_NATIVE_PILOT_MODEL=gemini-3.0-flash
```

### Bootstrap / actualizar LLM tras deploy

```bash
curl -X POST "https://ced-web-production.up.railway.app/v1/retell/native-pilot/bootstrap" \
  -H "X-Bootstrap-Secret: <RETELL_API_KEY>"
```

Re-ejecutar bootstrap tras cada deploy que cambie tools o prompt — actualiza el LLM staging en Retell.

### Probar por voz

1. URL: `?voicePilot=native`
2. Google Calendar y Gmail deben estar conectados en configuración de voz
3. Frases de prueba calendario: "¿qué tengo hoy?", "eventos de mañana"
4. Frases Gmail: "léeme mis correos", "correos importantes", "lee el correo de X"
5. Frases YouTube (requiere `YOUTUBE_API_KEY`): "pon Bohemian Rhapsody en YouTube", "pausa el video", "reanuda el video", "cierra YouTube"

### Métricas

```bash
GET /v1/retell/native-pilot/metrics      # latencias por tool
GET /v1/retell/native-pilot/call-metrics/{call_id}
```

---

## Notas técnicas

- Gateway: verificación `X-Retell-Signature`; `user_id` desde `call.metadata`.
- Prod intacto: `retell_custom_llm.py`, locks, standalone, orquestador r7.
- Agente prod: `CED Jarvis` | Staging: `CED Jarvis Native Pilot`.
