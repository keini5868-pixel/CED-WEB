# Fase 0 — Reporte de completitud

**Proyecto:** Castillo Digital Web (CED SaaS)  
**Fecha:** 2026-06-03  
**Estado:** ✅ Fase 0 completada (scaffold + contratos + documentación)

---

## 1. Estructura del proyecto creada

```
CED-WEB/
├── .github/workflows/ci.yml
├── apps/
│   ├── api/                    # FastAPI
│   │   ├── app/
│   │   │   ├── config.py
│   │   │   ├── main.py
│   │   │   ├── domain/plans.py # Planes + recargas + márgenes
│   │   │   └── routers/        # health, billing (stubs), usage (stub)
│   │   ├── migrations/001_initial_schema.sql
│   │   ├── requirements.txt
│   │   └── .env.example
│   └── web/                    # Next.js 15 App Router
│       ├── src/app/              # layout, home, login (placeholder)
│       ├── public/manifest.webmanifest  # PWA base
│       └── .env.example
├── packages/
│   ├── config/                 # TSConfig compartido
│   ├── types/                  # Planes, recargas, eventos HUD
│   └── ui/                     # tokens.css cyan #00e5ff
├── docs/
│   ├── ENV_SETUP.md
│   └── PRICING_RECHARGES.md
├── package.json                # pnpm + turbo
├── pnpm-workspace.yaml
├── turbo.json
├── MIGRATION_PLAN.md
└── README.md
```

---

## 2. Servicios configurados (pendiente de tus credenciales)

| Servicio | Estado Fase 0 | URL / notas |
|----------|---------------|-------------|
| **Supabase** | Documentado + SQL migración | Crear en dashboard.supabase.com |
| **Stripe** | Stubs API + env vars | dashboard.stripe.com/test |
| **Redis** | Env + schema uso | localhost o Upstash |
| **Vercel** | Listo para conectar repo | vercel.com |
| **Railway/Render** | Documentado | railway.app / render.com |
| **Resend** | Env vars | resend.com |
| **GitHub Actions** | CI básico web + api | `.github/workflows/ci.yml` |

**No se crearon cuentas por ti** — Fase 0 deja el scaffold y las guías.

---

## 3. URLs locales de desarrollo

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:3000 |
| API health | http://localhost:8000/health |
| API meta (planes + recargas + márgenes) | http://localhost:8000/v1/meta |
| API usage stub | http://localhost:8000/v1/usage/balance |

---

## 4. Variables de entorno que debes configurar

Copia desde `.env.example`:

### `apps/web/.env.local`

- `NEXT_PUBLIC_APP_URL`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`

### `apps/api/.env`

- `SUPABASE_*`, `STRIPE_*`, `REDIS_URL`
- `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`
- `SUPER_ADMIN_EMAILS` (tu email)
- `RESEND_API_KEY`

Detalle paso a paso: **`docs/ENV_SETUP.md`**

---

## 5. Decisiones implementadas en código

| Decisión | Ubicación |
|----------|-----------|
| Planes $39 / $99 / $249 | `packages/types`, `apps/api/domain/plans.py` |
| Límites 30 / 60 / 180 min día | `PLAN_LIMITS`, `PLANS` |
| Recargas con análisis margen | `docs/PRICING_RECHARGES.md`, `/v1/meta` |
| Warning 80% uso | `USAGE_WARNING_PERCENT` |
| Tablas usage/recharges/transactions | `migrations/001_initial_schema.sql` |
| Estética cyan + Orbitron/Inter | `packages/ui/tokens.css`, `apps/web` home |

### Precios de recarga — decisión pendiente tuya

| Pack | Promo (tu propuesta) | **Recomendado 50% margen** |
|------|----------------------|----------------------------|
| Booster 4h | $10 (40% margen) | **$12** |
| Power 10h | $20 (25% margen) | **$30** |
| Mega 30h | $50 (10% margen) | **$90** |

Ver análisis completo en `docs/PRICING_RECHARGES.md`.

---

## 6. Cómo probar Fase 0 en tu máquina

```powershell
cd C:\Users\keini\OneDrive\Escritorio\CED-WEB
pnpm install
cd apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..\..
pnpm dev:api
# Otra terminal:
pnpm dev:web
```

Abre http://localhost:3000 (landing HUD) y http://localhost:8000/v1/meta (JSON planes).

---

## 7. Próximos pasos — Fase 1 (Semanas 2-3)

1. Crear proyecto Supabase y ejecutar migración SQL  
2. Auth completo (registro, login, reset password, Google OAuth)  
3. Middleware Next.js: rol `super_admin` → botón 🏰 Panel Admin  
4. Layout dashboard CED vacío con anillos Three.js (placeholder)  
5. Conectar `@supabase/ssr` en `apps/web`  
6. Endpoint API validación JWT Supabase  
7. Inicializar repo GitHub y push  

---

## 8. Repositorio Git

Ejecuta en tu máquina (si aún no hay repo):

```powershell
cd C:\Users\keini\OneDrive\Escritorio\CED-WEB
git init
git add .
git commit -m "feat: Fase 0 — monorepo Castillo Digital Web"
```

---

## 9. Riesgos / bloqueos

- **OneDrive:** puede bloquear `pnpm install` o `.next` — considera mover repo fuera de OneDrive si hay errores de permisos.  
- **Next.js 16:** usamos **Next.js 15** (estable); actualizar a 16 cuando GA.  
- **Gemini model name:** spec menciona `gemini-3.1-flash-live` — validar ID exacto en Google AI docs al iniciar Fase 2.

---

*Legacy `CED/` no fue modificado.*
