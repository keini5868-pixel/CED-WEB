# Video Edit Module — Piloto

Módulo aislado de edición de video con tokens por duración real.

## Activación (default OFF)

| Capa | Variable / flag |
|------|-----------------|
| Web UI | `?videoEditModule=pilot` **o** `NEXT_PUBLIC_VIDEO_EDIT_MODULE_PILOT=true` |
| API | `VIDEO_EDIT_MODULE_PILOT=true` |
| Header obligatorio | `X-CED-Video-Edit-Pilot: 1` (el cliente lo envía; el BFF lo reenvía) |
| Veo Lite | `VIDEO_EDIT_VEO_ENABLED=true` (sigue siendo opt-in; criterio estricto) |

Kill-switch: sin env API o sin header → 404. Sin query/env web → no aparece en el rail.

## Economía

- `$1 = 100 tokens` (crédito 1:1 al comprar pack)
- `1 segundo de salida = 1 token`
- Mínimo facturable: **30 segundos**
- Soft cap: **2 renders/día**
- Packs: **$10 / $20 / $50**
- Margen objetivo: **30–35%** (venta $0.01/s vs COGS ~$0.007/s)

## Stack

- Shotstack Edit + Ingest (upload firmado → render → URL MP4)
- `SHOTSTACK_API_KEY` + `SHOTSTACK_ENV=stage|v1`
- `SONILO_API_KEY` — Text→SFX real en el render (si falta, solo cues planificados + cortes visuales)
- Veo 3.1 Lite solo si hay hard-cut + flag + cupo

## Soft cap piloto

10 renders/día (subido para validación; bajar a 2 en producción).

## Flujo live

1. Cliente envía `multipart/form-data` con `video` + `script` + `duration_sec`
2. API descuenta tokens
3. Sube a Shotstack Ingest, construye Edit JSON (cortes por escenas + fades)
4. Poll render → `result_url` en el panel

## Migración

Aplicar en Supabase: `apps/api/migrations/025_video_edit_tokens.sql`

## Stripe (opcional)

Si no hay `STRIPE_PRICE_VIDEO_EDIT_{10,20,50}`, Checkout usa `price_data` ad-hoc.
Webhook: `checkout_type=video_edit_tokens` → acredita tokens.

## Probar

1. Railway API: `VIDEO_EDIT_MODULE_PILOT=true`
2. Abrir dashboard con `?videoEditModule=pilot`
3. Rail lateral → **VIDEO**
4. Comprar pack / simular crédito en tests
5. Subir video + guion → Generar (dry-run sin `SHOTSTACK_API_KEY`)

No cableado a voz ni chat público.
