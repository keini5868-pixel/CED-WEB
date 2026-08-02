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

- Shotstack (edit/render) — PAYG en piloto
- Sonilo **Text → SFX** (3–5 cues), no Video→SFX
- Veo 3.1 Lite solo si hay hard-cut + flag + cupo

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
