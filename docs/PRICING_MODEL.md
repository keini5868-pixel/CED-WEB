# Resumen ejecutivo — Cambio a producto único (2026-06-03)

Keini simplificó el modelo: **un solo plan CED Élite** con dos fases de precio y **recargas flexibles**.

## Decisiones codificadas

| Tema | Valor |
|------|-------|
| Founding (cupos 1–50) | $149/mes, precio bloqueado de por vida |
| Launch (51+) | $249/mes |
| Gemini Live | 120 min/día (audio + video) |
| Claude texto | Ilimitado en todos |
| Recarga margen | 40% Keini / 60% saldo cliente |
| Recarga rango | $5 – $500, botones $10/$25/$50/$100 |
| Saldo recarga | No expira |

## Archivos actualizados

- `packages/types/src/index.ts`
- `apps/api/app/domain/plans.py`
- `apps/api/app/routers/health.py` (+ `/v1/recharge/quote`)
- `apps/api/migrations/001_initial_schema.sql`
- `apps/web/src/app/page.tsx`
- `docs/PRICING_RECHARGES.md`

## Eliminado

- Planes Starter ($39), Pro ($99), multi-plan UI
- Paquetes fijos Booster / Power / Mega
