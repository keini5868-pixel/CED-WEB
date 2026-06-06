# Fase 1 — Autenticación y HUD base

Preparación sin credenciales activas. Al recibir las claves, conecta en `apps/web/.env.local`.

## Variables (`apps/web/.env.local`)

```env
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPER_ADMIN_EMAILS=keini@castillodigital.com
```

`SUPER_ADMIN_EMAILS` es solo servidor (no uses `NEXT_PUBLIC_` salvo pruebas locales).

## Supabase Dashboard

1. **Authentication → URL Configuration**
   - Site URL: `http://localhost:3000` (prod: tu dominio)
   - Redirect URLs:
     - `http://localhost:3000/auth/callback`
     - `http://localhost:3000/**` (desarrollo)

2. **Authentication → Providers → Google**
   - Client ID / Secret de Google Cloud Console
   - Authorized redirect URI en Google: la URL que muestra Supabase

3. **SQL Editor** — ejecutar en orden:
   - `apps/api/migrations/001_initial_schema.sql`
   - `apps/api/migrations/002_profile_on_signup.sql` (opcional trigger)

4. **Rol super_admin** (elige una):
   - Email en `SUPER_ADMIN_EMAILS` (recomendado para Keini)
   - `app_metadata.role = "super_admin"` en el usuario
   - Columna `profiles.role = 'super_admin'`

## Rutas

| Ruta | Descripción |
|------|-------------|
| `/login` | Email + contraseña, Google OAuth |
| `/register` | Alta con trial 7 días |
| `/auth/callback` | Intercambio código OAuth / confirmación email |
| `/app` | Dashboard HUD (protegido con sesión) |
| `/admin` | Panel admin (solo `super_admin`) |

## Middleware

`apps/web/src/middleware.ts` refresca cookies Supabase y:

- Redirige a `/login` si no hay sesión en `/app` o `/admin`
- Redirige a `/app` si ya hay sesión en `/login` o `/register`
- Bloquea `/admin` si el email/rol no es super admin

## UI compartida (`@ced/ui`)

- `CedButton`, `CedInput`, `HudPanel` — estética cyan HUD
- Botón **🏰 Panel Admin** en header: `AdminPanelButton` solo si `isSuperAdmin`

## Stripe (Fase 7)

Por ahora solo variables en `.env.example`. No hay checkout en Fase 1.

## Verificación local

```powershell
cd C:\Users\keini\OneDrive\Escritorio\CED-WEB
npx pnpm@9.15.0 install
pnpm dev:web
```

- Sin `.env.local`: landing + HUD `/app` en modo vista previa
- Con Supabase: login, Google, `/app` protegido, admin solo para tu email
