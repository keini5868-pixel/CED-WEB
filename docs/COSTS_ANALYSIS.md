# CED — Auditoría de costos OpenAI (borrador)

> Fecha: 2026-05-28 · Estado: **pre-implementación**  
> Objetivo: validar márgenes antes de migrar Gemini → OpenAI Realtime.

---

## 1. Resumen ejecutivo

| Pregunta | Respuesta |
|----------|-----------|
| ¿Viable con límites 15/30/60/90 min? | **Sí, condicionado** — solo si se usa **Realtime Mini**, prompts cortos, y uso medio <70% del tope diario. |
| ¿Los márgenes $17–74 del doc son realistas? | **Optimistas** para usuario que agota el cupo; **razonables** si el uso medio es ~40–50% del límite. |
| ¿Migrar ya? | **No.** Primero: actualizar límites en código + feature flag + beta interna OpenAI. |

---

## 2. Precios OpenAI Realtime (referencia 2026)

OpenAI cobra **tokens de audio**, no un flat $/min fijo.

| Modelo | Audio input / 1M | Audio output / 1M | Notas |
|--------|------------------|-------------------|--------|
| `gpt-4o-mini-realtime-preview` | ~$10 | ~$20 | Recomendado para CED fase 1 |
| `gpt-4o-realtime-preview` | ~$32 | ~$64 | Premium; margen más apretado |
| `gpt-realtime-2` | $32 | $64 | Flagship; solo si Mini no basta |

**Tokenización audio (aprox.):**
- Usuario: ~600 tokens/min de audio
- Asistente (CED): ~1.200 tokens/min de audio
- System prompt largo + tools → **+50–200%** costo (medido en pruebas de terceros)

**Estimación práctica por minuto de sesión conectada** (Mini + prompt CED moderado):

| Perfil | $/min sesión |
|--------|----------------|
| Optimista (respuestas cortas, poco tool use) | $0.12 – $0.18 |
| Realista (Jarvis normal, tools ocasionales) | $0.20 – $0.35 |
| Pesimista (respuestas largas, cámara, búsquedas) | $0.40 – $0.60+ |

Fuente: [OpenAI Realtime costs](https://developers.openai.com/api/docs/guides/realtime-costs), benchmarks públicos 2025–2026.

---

## 3. Costo mensual de VOZ por plan (solo OpenAI Realtime Mini)

Fórmula: `minutos_mes = min_día × 30 × tasa_uso_real`

| Plan | Límite min/día | Min/mes (100% uso) | Costo voz @ $0.20/min | Costo voz @ $0.35/min |
|------|----------------|--------------------|-----------------------|------------------------|
| Trial / Starter | 15 | 450 | **$90** | **$158** |
| Pro | 30 | 900 | **$180** | **$315** |
| Élite | 60 | 1.800 | **$360** | **$630** |
| Founding | 90 | 2.700 | **$540** | **$945** |

### Con uso medio realista (50% del cupo)

| Plan | Ingreso | Voz ~50% @ $0.20 | Voz ~50% @ $0.35 | Margen bruto voz |
|------|---------|------------------|------------------|------------------|
| Starter $30 | $30 | ~$45 ❌ | ~$79 ❌ | Negativo si agotan |
| Pro $59 | $59 | ~$90 ❌ | ~$158 ❌ | Negativo si agotan |
| Élite $99 | $99 | ~$180 ❌ | ~$315 ❌ | Negativo si agotan |
| Founding $149 | $149 | ~$270 ❌ | ~$473 ❌ | Negativo si agotan |

**Conclusión crítica:** si un usuario **usa todo** su cupo diario de voz, el margen de **solo voz** es negativo con Realtime Mini.  
Los números del doc ($13/$25/$50/$75) solo cuadran si:
- el usuario usa **~2–4 min/día** de media (no 15), o
- el costo efectivo es **~$0.03–0.05/min** (no observado con prompt + tools).

---

## 4. Escenario sostenible (recomendado)

Objetivo: **margen bruto API > 40%** incluyendo voz + chat Claude + imágenes.

| Plan | Ingreso | Presupuesto API total/mes | Voz (50% cupo) | Chat Claude | Imágenes | Margen |
|------|---------|---------------------------|----------------|-------------|----------|--------|
| Starter $30 | $30 | $12 | ~$8 | ~$2 | ~$0.12 | ~$10 ✅ |
| Pro $59 | $59 | $24 | ~$16 | ~$4 | ~$1 | ~$35 ✅ |
| Élite $99 | $99 | $40 | ~$32 | ~$5 | ~$3 | ~$59 ✅ |
| Founding $149 | $149 | $60 | ~$48 | ~$6 | ~$6 | ~$89 ✅ |

Para cuadrar esta tabla hace falta:
1. **Límites duros** en servidor (no solo UI).
2. **Respuestas cortas** en voz (max tokens bajo).
3. **System prompt compacto** (<500 tokens).
4. **Claude solo** para análisis profundo, no en cada turno.
5. **Monitoreo** por usuario; kill switch si costo > 2× ingreso.

---

## 5. Nuevos límites propuestos vs código actual

| Plan | Voz/día ACTUAL | Voz/día NUEVO | Imágenes ACTUAL | Imágenes NUEVO |
|------|----------------|---------------|-----------------|----------------|
| Trial | 30 min | **15 min** | (élite) | std/HD según plan |
| Free | 0 / 50 chat | igual ✅ | 0 | 0 ✅ |
| Starter | 30 min | **15 min** | 20/mes | **3 std** |
| Pro | 60 min | **30 min** | 50/mes | **10 std + 3 HD** |
| Élite | 120 min | **60 min** | 100/mes | **20 std + 8 HD** |
| Founding | **9999** | **90 min** | ilimitado | **40 std + 15 HD** |

**Acción inmediata (sin OpenAI):** bajar Founding 9999→90 y alinear `plans.py` + `/pricing`.

---

## 6. Recargas — recalcular horas extra

Hoy: `GEMINI_COST_PER_HOUR_USD = 1.50` → $10 recarga ≈ 4 h.

Con OpenAI Mini ~$0.20/min → **$12/h** costo API → recargas deben ofrecer **menos horas** o **subir precio**:

| Recarga | Horas actuales (doc) | Horas sugeridas @ $12/h costo |
|---------|----------------------|-------------------------------|
| $10 (60% = $6) | 4 h | **~0.5 h (30 min)** |
| $20 | 9 h | **~1 h** |
| $40 | 20 h | **~2 h** |
| $100 | 55 h | **~5 h** |

O mantener horas del doc subiendo precios de recarga (~3–4×).

---

## 7. Costos adicionales no incluidos en el doc

| Servicio | Estimado/usuario/mes |
|----------|----------------------|
| Claude chat (Sonnet) | $1 – $8 según uso |
| Tavily búsquedas | $0.50 – $3 |
| Imágenes OpenAI | $0.04 std / $0.17 HD × cuota |
| Supabase + Railway | fijo, diluido por usuario |

---

## 8. Inventario Gemini (resumen)

~25+ archivos backend/frontend. Críticos:
- `apps/api/app/services/gemini_live.py`
- `apps/web/src/lib/voice/live/ced-live-client.ts`
- `apps/web/src/hooks/useCedVoiceSession.ts`

**Estrategia:** `VOICE_PROVIDER=gemini|openai` — no eliminar Gemini hasta beta estable.

---

## 9. Respuestas a las 5 preguntas del plan

1. **¿Viabilidad 15/30/60/90?** Condicionalmente sí con Mini + uso medio + enforcement; no con uso máximo diario sin recargas.
2. **¿Branch o prod?** Branch `feat/openai-realtime` + staging Railway.
3. **¿Rollback?** Feature flag; revert web; Gemini fallback automático.
4. **¿Tiempo real?** 25–35 días laborables (no 13–15).
5. **¿Riesgos?** Costos impredecibles, móvil/audio, Founding 9999→90, dual provider.

---

## 10. Próximos pasos (orden)

1. ✅ Este documento  
2. Actualizar `plans.py` + UI con nuevos límites (Gemini sigue)  
3. Beta interna OpenAI Realtime (5 usuarios, medir $/min real 7 días)  
4. Ajustar límites o precios según datos reales  
5. Migración gradual con fallback  

**No eliminar Gemini hasta paso 4.**
