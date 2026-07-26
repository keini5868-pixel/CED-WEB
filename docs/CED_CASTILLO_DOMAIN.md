# Dominio ced-castillo.com → frontend (Railway)

## Situación

- DNS de `ced-castillo.com` está verificado.
- Hoy el **apex** responde en el servicio **API** (`{"detail":"Not Found"}` en `/`).
- El frontend real vive en el servicio **WEB** (`cedweb-production.up.railway.app`).
- `/privacy` y `/terms` ya existen en el frontend Next.js **y** (respaldo) en la API.

## Objetivo

1. `https://ced-castillo.com/` → UI pública de CED (sin login).
2. Google OAuth brand: nombre **CED** + explicación clara de qué hace la app en la home.
3. `https://ced-castillo.com/privacy` y `/terms` siguen OK (páginas Next del web).
4. **Canónico único:** cualquier `http://`, `www.` o legacy → **301** a `https://ced-castillo.com`.

## Redirect canónico (www / http)

El middleware Next (`apps/web/src/lib/canonical-host.ts`) hace **301** a
`https://ced-castillo.com` cuando recibe:

- `https://www.ced-castillo.com/...`
- `http://ced-castillo.com/...` (Railway ya fuerza HTTPS en apex; el middleware refuerza)
- hosts legacy `*.castillodigital.com`

Para que `www` funcione (hoy no resolvía DNS), el dominio
`www.ced-castillo.com` está añadido al servicio **WEB** en Railway. En tu DNS
añade:

| Tipo | Nombre / host | Valor |
|------|----------------|--------|
| CNAME | `www` | `8rnqkzoa.up.railway.app` |
| TXT | `_railway-verify.www` | `railway-verify=bd591cd6af731c15f5f2bde95f2c23bc81a86e5fa48a77a95f8af4c51c6c8053` |

(Si Railway regenera el target CNAME, usa el valor actual de
`railway domain status www.ced-castillo.com -s "@ced/web"`.)

Tras propagar DNS (~minutos):

```bash
curl -sI http://www.ced-castillo.com/ | head
curl -sI https://www.ced-castillo.com/ | head
# Esperado: HTTP/1.1 301  Location: https://ced-castillo.com/
```

En Google Search Console: dominio preferido / “Change of address” hacia
`https://ced-castillo.com` (sin www) para acelerar la reindexación.

## Pasos en Railway (manual — requiere acceso al proyecto)

### A) Mover el dominio custom del API al WEB

1. Abre el servicio **API** (CED-WEB-PRODUCTION / el que tiene `railway.api.toml`).
2. **Settings → Networking / Custom Domain** → elimina `ced-castillo.com` (y `www` si está ahí).
3. Abre el servicio **WEB** (CED-WEB / `railway.web.toml` / Docker `apps/web`).
4. **Settings → Networking → Custom Domain** → añade:
   - `ced-castillo.com`
   - opcional: `www.ced-castillo.com`
5. Copia el target CNAME / instrucciones que Railway muestre.
6. En tu DNS (donde ya verificaste el dominio), apunta el apex/`www` al **target del servicio WEB** (no al de la API). Si Railway muestra un CNAME distinto al anterior, actualízalo.
7. Espera propagación (minutos; a veces más).

### B) API en subdominio (recomendado)

Para no perder la API pública:

1. En el servicio **API**, añade custom domain: `api.ced-castillo.com`
2. CNAME DNS → target Railway del API
3. Variables a actualizar:
   - API: `API_PUBLIC_URL=https://api.ced-castillo.com`
   - API: `WEB_PUBLIC_URL=https://ced-castillo.com`
   - API: `CORS_ORIGINS` incluir `https://ced-castillo.com`
   - WEB: `NEXT_PUBLIC_APP_URL=https://ced-castillo.com`
   - WEB: `NEXT_PUBLIC_API_URL=https://api.ced-castillo.com` (o la URL Railway API si aún no usas el subdominio)
   - WEB: `CED_API_URL` / proxy si aplica

### C) Google / Supabase Auth (cierre al 100%)

- Google Cloud OAuth: Authorized domains → `ced-castillo.com`
- Consent screen / homepage URL → `https://ced-castillo.com`
- Privacy / Terms → `https://ced-castillo.com/privacy` y `/terms`

**Supabase → Authentication → URL Configuration**

| Campo | Valor |
|-------|--------|
| Site URL | `https://ced-castillo.com` |
| Redirect URLs | `https://ced-castillo.com/**` |
| | `https://ced-castillo.com/auth/callback` |
| | `https://ced-castillo.com/reset-password` |
| | `https://cedweb-production.up.railway.app/**` |

No usar `app.castillodigital.com` (DNS muerto).

**Supabase → Authentication → SMTP (Resend — obligatorio en prod)**

El SMTP gratis de Supabase limita ~2 emails/hora (recovery/signup). Configurar:

| Campo | Valor |
|-------|--------|
| Host | `smtp.resend.com` |
| Port | `465` |
| User | `resend` |
| Pass | API key `re_...` (también en Railway `RESEND_API_KEY`) |
| Sender | `CED <noreply@ced-castillo.com>` |

Luego **Authentication → Rate Limits** → subir envío de emails (ej. 100/h).

Verificar dominio en Resend (DKIM/SPF) para `ced-castillo.com`.

## Verificación

```bash
# Home = HTML de Next con marca CED (no JSON de FastAPI)
curl -sI https://ced-castillo.com/
curl -s https://ced-castillo.com/ | head

# Legales
curl -sI https://ced-castillo.com/privacy
curl -sI https://ced-castillo.com/terms

# API (si usas subdominio)
curl -s https://api.ced-castillo.com/health
```

Esperado en `/`:

- Status 200
- HTML con título/marca **CED** y texto explicando el asistente
- Sin `{"detail":"Not Found"}`

Esperado en `/privacy` y `/terms`: 200 + texto legal completo.

## Nota

Este archivo no mueve el dominio solo: el binding Custom Domain es acción en el dashboard de Railway + DNS. El código de la home pública ya está preparado para la verificación de marca de Google.
