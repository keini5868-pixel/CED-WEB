# Sentinel Privacy (producto aparte)

## Identidad

- **Marca:** Sentinel Privacy
- **Qué es:** suscripción de sellos verificables (hash + tiempo) alineada con CED Shield / Midnight.
- **Qué no es:** plan CED (Jarvis, chat, imágenes). Misma cuenta de usuario; facturación y tabla propias.

## Precios (USD/mes)

| Plan ID | Precio | Sellos/mes (volumen) |
|---------|--------|----------------------|
| `sentinel_solo` | $12 | 10 |
| `sentinel_pro` | $29 | 40 |
| `sentinel_business` | $200 | 200 |

**CED:** cada plan de pago incluye cupo base de sellos (interno; UI: «Privacidad verificable incluida»). Founding incluye el techo (200/mes). Sentinel Business amplía volumen para quien no necesita Founding.

Landing: `/sentinel-privacy`

## Stripe

- Checkout: `POST /v1/billing/checkout/sentinel-privacy` con `{ "plan_id": "sentinel_solo" | ... }`
- Metadata: `checkout_type=sentinel_privacy`, `product_line=sentinel_privacy`
- Webhook: no llama a `upsert_paid_subscription` de CED; usa `sentinel_privacy_subscriptions`
- Env opcional: `STRIPE_PRICE_SENTINEL_SOLO`, `_PRO`, `_BUSINESS` (si faltan, Checkout crea `price_data`)

## Base de datos

Migración `046_sentinel_privacy_subscriptions.sql` — tabla `sentinel_privacy_subscriptions`.

## Qué está activo ahora

- **HUD** `/dashboard/sentinel`: interruptores persistidos en el dispositivo.
- **Chat / avanzado:** si explosivos, armas o autolesión están ON, el texto no se envía al modelo.
- **Extensión MV3** (`apps/web/public/sentinel-extension`): malware (DNR), DoH Cloudflare, quitar rastreadores de URLs, categorías en búsquedas. Publicada en Chrome Web Store: [Sentinel Privacy for CED](https://chromewebstore.google.com/detail/sentinel-privacy-for-ced/lljjmaaeaablafifigijmfclaakglphi) (ID `lljjmaaeaablafifigijmfclaakglphi`, v0.1.0, 18 oct 2026).
- **Equipo:** enlace de política (sin historial de URLs). Workspace puede forzar ese ID.
- **Jueces / AKINDO:** el loop sigue siendo `/shield` (sin login). Sentinel refuerza el dual-ledger: consultas locales vs sello hash.

## Shield

- Kill-switch global: `CED_SHIELD_ENABLED` (prod = false).
- Con Shield ON, `/v1/shield/seal` exige suscripción Sentinel activa y descuenta 1 sello al sellar.
- No se activa al abrir el módulo HUD. Jarvis / voz / Retell no entran.

## Centinela Ops

No confundir con **Centinela Ops** (QA imagen/voz). Sentinel Privacy es producto comercial de privacidad.
