# Módulo Automatización (piloto)

Embudo **Instagram → Facebook → WhatsApp** sin builder visual. La personalización es conversacional (voz/chat con CED).

## Kill-switches

| Variable | Default | Rol |
|----------|---------|-----|
| `AUTOMATION_MODULE_ENABLED` | `false` | API + worker |
| `AUTOMATION_IG_FB_LIVE_ENABLED` | `false` | Si OFF → dry-run (log sin envíos IG/FB) |
| `NEXT_PUBLIC_AUTOMATION_MODULE_ENABLED` | unset | UI sin query |
| Query `?automationModule=pilot` | — | Muestra el módulo en el rail |
| Header `X-CED-Automation-Pilot: 1` | — | Rutas autenticadas `/v1/automation-pilot/*` |

Extras:

- `AUTOMATION_WEBHOOK_VERIFY_TOKEN` (fallback: `WHATSAPP_VERIFY_TOKEN`)
- `INSTAGRAM_APP_SECRET` / `META_APP_SECRET` (firma `X-Hub-Signature-256`)
- `AUTOMATION_DEFAULT_WHATSAPP_E164` (wa.me en respuestas)

## Webhooks Meta

- `GET|POST /webhooks/instagram`
- `GET|POST /webhooks/facebook`
- `GET|POST /webhooks/meta` (alias)

Setup: subscribe con `hub.verify_token`. El POST encola en hilo daemon (mismo patrón WhatsApp inbound) y **no** ejecuta Graph en el request HTTP.

## Migración

`apps/api/migrations/040_automation_module.sql` → `ced_automations`, `ced_leads`, `ced_automation_events`.

## Cuotas activas

| Plan | Activas |
|------|---------|
| Free | 0 |
| Starter | 2 |
| Pro | 5 |
| Élite / Founding | ilimitado |

## Fase 1 estado

- Tarjetas curadas IG/FB/WA + preview conversacional
- Dry-run IG/FB hasta Advanced Access (`instagram_manage_messages`, `pages_messaging`)
- Comentarios: OAuth ya pide `instagram_manage_comments`
- WhatsApp nurturing/días: schema + tarjetas listas; envío real vía stack WA existente en fases siguientes

## Checklist usuario (Meta)

1. Roles → evaluador Instagram en cuenta tester
2. Validar dry-run con tester
3. Enviar revisión formal a Meta
4. Poner `AUTOMATION_IG_FB_LIVE_ENABLED=true` (sin redeploy de código)
