# Piloto Retell LLM nativo — clima (staging)

Agente **separado** de producción. Producción (`RETELL_AGENT_ID`, Custom LLM r7) no se modifica.

## Variables Railway (piloto)

```env
# IDs del agente staging — se obtienen con bootstrap (ver abajo)
RETELL_NATIVE_STAGING_AGENT_ID=
RETELL_NATIVE_STAGING_LLM_ID=
RETELL_NATIVE_PILOT_MODEL=gemini-3.0-flash
```

Opcional frontend (sin query param):

```env
NEXT_PUBLIC_RETELL_NATIVE_PILOT=true
```

## Bootstrap del agente staging (una vez)

```bash
curl -X POST "https://<API_PUBLIC_URL>/v1/retell/native-pilot/bootstrap" \
  -H "X-Bootstrap-Secret: <RETELL_API_KEY o RETELL_BOOTSTRAP_SECRET>"
```

Copiar `agent_id` y `llm_id` de la respuesta a Railway.

## Cómo probar por voz

1. Abrir la app con **`?voicePilot=native`** en la URL (ej. `https://app.castillodigital.com/?voicePilot=native`).
2. Iniciar sesión e iniciar voz — verás **"Piloto nativo — conectando…"**.
3. La llamada usa `POST /v1/retell/register-call-native-pilot` (agente staging, `retell-llm`).
4. Producción sigue en la URL normal sin query param.

## Protocolo de pruebas (r2–r7)

Repetir **en ambos sistemas** (prod vs piloto) y anotar resultados:

| # | Secuencia | Qué observar |
|---|-----------|--------------|
| 1 | "¿Cómo está el clima hoy?" / "dame información sobre el clima" | Datos reales, una sola respuesta |
| 2 | "calidad de aire" (sin "del") | Activa get_environment, no charla vacía |
| 3 | Tras clima → "Ok, gracias" | Charla casual, **sin** re-ejecutar clima |
| 4 | Tras clima → "¿Estás ahí?" / "Sí, me escuchas" | Check-in casual, **sin** clima duplicado |
| 5 | "Charlotte" / "Carolina del Norte" tras pregunta de aire | Follow-up de ubicación |
| 6 | Hablar rápido / interrumpir durante respuesta | Sin solapamiento ni arrastre de turno |
| 7 | Desahogo personal (dolor de estómago, etc.) | Tono CED, sin tools |

## Métricas post-llamada

```bash
# Estado del piloto
GET /v1/retell/native-pilot/status

# Latencias acumuladas del gateway get_environment
GET /v1/retell/native-pilot/metrics

# Detalle de una llamada (transcript Retell + latencias locales)
GET /v1/retell/native-pilot/call-metrics/{call_id}
```

---

## Reporte comparativo (plantilla)

Completar tras pruebas de voz reales.

### Configuración

| | Producción (r7) | Piloto nativo |
|--|-----------------|---------------|
| Engine | `custom-llm` WebSocket | `retell-llm` |
| Modelo LLM | Gemini 2.5 Flash (API key propia) | Gemini 3.0 Flash (Retell) |
| Voz | Jarvis (`RETELL_VOICE_ID`) | Misma voz (copiada del agente prod) |
| Tool clima | Orquestador + anchors/heurísticas | `get_environment` Custom Function |

### Latencia módulo clima (ms)

| Frase | Prod r7 | Piloto nativo |
|-------|---------|---------------|
| "¿Cómo está el clima hoy?" | _pendiente_ | _ver `environment_avg_latency_ms`_ |
| "calidad de aire" | _pendiente_ | _pendiente_ |
| Follow-up ubicación | _pendiente_ | _pendiente_ |

### Bugs de turnos (r2–r7)

| Bug | Prod r7 | Piloto nativo |
|-----|---------|---------------|
| Solapamiento de audio | | |
| Arrastre de turno anterior | | |
| Repetición clima no solicitada | r6–r7 parcheado | _pendiente_ |
| Silencio post-clima | r5 parcheado | _pendiente_ |

### Charla casual

| Frase | Prod r7 | Piloto nativo |
|-------|---------|---------------|
| "Ok, gracias" | | |
| "¿Estás ahí?" | | |
| Desahogo personal | | |

### Costo por minuto (estimado)

| | Prod r7 | Piloto nativo |
|--|---------|---------------|
| LLM | Gemini 2.5 Flash directo Google (~$0.15/1M input*) | Retell Gemini 3.0 Flash ~$0.027/min Retell |
| Infra turnos | Custom WS + API compute | Incluido en Retell |
| **Total observado** | _medir en Google Cloud + Railway_ | _medir en Retell dashboard call cost_ |

\* Google pricing varía; comparar minutos reales de la misma duración de llamada.

### Recomendación

- [ ] **Proceder a Fase 3** (tools de lectura: calendario, Gmail) — piloto estable
- [ ] **Iterar piloto** — problemas encontrados: ___
- [ ] **Quedarse en Custom LLM reforzado** — razón: ___

---

## Notas técnicas

- Gateway: `POST /v1/retell/tools/get_environment` con verificación `X-Retell-Signature`.
- `user_id` siempre desde `call.metadata` (register-call), nunca desde args LLM.
- Código prod intacto: `retell_custom_llm.py`, locks, standalone, orquestador.
- Agente prod: `CED Jarvis` | Staging: `CED Jarvis Native Pilot`.
