# Informe Fase 1 — Auth + HUD base

**Estado:** Conectado (Supabase Auth + DB migrada). Stripe: revisar clave test en Dashboard.

## Entregables

| # | Item | Ubicación |
|---|------|-----------|
| 1 | Auth SSR `@supabase/ssr` | `apps/web/src/lib/supabase/*`, `middleware.ts` |
| 2 | Login / registro / OAuth callback | `components/auth/*`, `/auth/callback` |
| 3 | Dashboard HUD vacío | `components/hud/*`, `/app` |
| 4 | UI cyan Tony Stark | `packages/ui` — `CedButton`, `CedInput`, `HudPanel` |
| 5 | Rol `super_admin` vs `client` | `lib/auth/roles.ts`, `session.ts` |
| 6 | Botón 🏰 Panel Admin | `AdminPanelButton.tsx` (solo Keini / lista emails) |

## Conexión (28 may 2026)

- [x] `apps/web/.env.local` y `apps/api/.env` configurados (gitignored)
- [x] Migraciones `001` + `002` aplicadas en Supabase
- [x] `GET http://localhost:8000/v1/integrations` — comprobar Supabase DB + Stripe
- [ ] Google OAuth en Supabase Dashboard (si aún no está)
- [ ] Stripe `sk_test_...` válido (la clave actual falló autenticación — copiar de nuevo modo Test)
- [ ] Registrarte con **keini@castillodigital.com** para ver 🏰 Panel Admin

## Comandos

```powershell
npx pnpm@9.15.0 install
pnpm dev:web    # :3000
pnpm dev:api    # :8000
pnpm typecheck  # monorepo
```

## Siguiente fase

**Fase 2:** Gemini Live + orbe central (Three.js / WebRTC).
