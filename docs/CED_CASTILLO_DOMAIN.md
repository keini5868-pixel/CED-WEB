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

### C) Google / Supabase

- Google Cloud OAuth: Authorized domains → `ced-castillo.com`
- Consent screen / homepage URL → `https://ced-castillo.com`
- Privacy / Terms → `https://ced-castillo.com/privacy` y `/terms`
- Supabase Auth: Site URL + Redirect URLs con `https://ced-castillo.com/**`

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
