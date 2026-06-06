# CED — Guía de deploy a producción

Documento maestro para las 7 fases. **Fase 1 completada en código.**

---

## Fase 1 — Preparación ✅ (código)

### Hecho en el repo

| Item | Archivo / acción |
|------|------------------|
| Build monorepo | `pnpm build` (fix tsconfig `@ced/types`) |
| Variables prod | `.env.production.example` |
| CORS estricto prod | `apps/api/app/config.py` + `main.py` |
| Logging JSON prod | `apps/api/app/logging_setup.py` |
| Headers seguridad API | `apps/api/app/middleware/security.py` |
| Request logging | `apps/api/app/middleware/request_logging.py` |
| Rate limiting | SlowAPI 120 req/min (configurable) |
| `/health` exempt | `apps/api/app/routers/health.py` |
| `/v1/integrations` protegido | Solo super admin |
| OpenAPI off en prod | `docs_url=None` si `APP_ENV=production` |
| Headers Next.js | `apps/web/next.config.ts` |
| Vercel monorepo | `vercel.json` |
| Railway Docker | `apps/api/Dockerfile` + `railway.toml` |

### Validar localmente

```powershell
cd C:\Users\keini\OneDrive\Escritorio\CED-WEB
pnpm build
pnpm typecheck

cd apps\api
pip install -r requirements.txt
$env:APP_ENV="production"
$env:CORS_ORIGINS="http://localhost:3000"
$env:WEB_PUBLIC_URL="http://localhost:3000"
python -m uvicorn app.main:app --port 8000
# GET http://localhost:8000/health → {"status":"ok","env":"production"}
```

---

## Decisiones recomendadas

### 1. Dominio (3 opciones)

| Dominio | Pros | Contras |
|---------|------|---------|
| **castillodigital.com** | Marca completa, profesional, coherente con email actual | Puede estar ocupado / caro |
| **cedcastillo.com** | Corto, memorable, disponible con más probabilidad | Menos SEO de marca “Castillo Digital” |
| **useced.com** o **ced.ai** | Muy corto para producto SaaS | Menos identidad “castillo”; .ai caro |

**Recomendación:** `castillodigital.com` (app.) + `api.castillodigital.com` si está libre. Si no, `cedcastillo.com`.

### 2. Railway vs Render

| | Railway | Render |
|---|---------|--------|
| DX | Excelente, logs, variables, deploy rápido | Muy bueno, similar |
| FastAPI | Docker nativo, healthchecks | Docker / native Python |
| Escala | Pay-as-you-go, sin sleep en plan pago | Free tier duerme (malo para voz 24/7) |
| Precio inicial | ~$5–20/mes según RAM/CPU | Free duerme; paid ~$7+ |

**Recomendación: Railway** para CED — voz + webhooks Stripe + OAuth Meta necesitan **siempre encendido**. Render free no sirve para producto $149–249/mes.

### 3. Supabase Free vs Pro ($25/mes)

| Plan | Cuándo |
|------|--------|
| **Free** | Hasta ~50 usuarios beta, poco tráfico, backups manuales OK |
| **Pro** | Primeros clientes pagos, RLS auditada, backups diarios, soporte, >500MB DB, picos de auth |

**Upgrade cuando:** lances founding members pagos o superes 100 MAU. No antes de tener 5–10 clientes reales.

### 4. ¿GitHub primero?

**Sí, obligatorio** para Vercel + Railway con CI. El repo **aún no tiene git** en tu máquina.

Pasos tuyos (~20 min):

1. Crear repo privado `castillo-digital-web` en GitHub
2. En la carpeta CED-WEB:
   ```powershell
   git init
   git add .
   git commit -m "Initial production-ready CED Web"
   git remote add origin https://github.com/TU_USUARIO/castillo-digital-web.git
   git push -u origin main
   ```
3. Verificar `.gitignore` excluye `.env`, `.env.local`, `apps/api/.env`

### 5. Stripe test_mode → live

**Sí:** arrancamos en **test_mode** (`sk_test_`, `pk_test_`).

Migración a live cuando:

- [ ] Smoke tests prod OK
- [ ] Webhook test verificado
- [ ] Checkout founding + regular probados
- [ ] Términos legales / facturación listos

---

## Lo que necesitas hacer tú (resumen)

| Acción | Dónde | Costo aprox. | Tiempo |
|--------|-------|--------------|--------|
| Comprar dominio | Cloudflare Registrar / Namecheap | $12–40/año | 15 min |
| Cuenta GitHub | github.com | Gratis | 5 min |
| Cuenta Vercel | vercel.com (login GitHub) | Gratis → Pro si hace falta | 10 min |
| Cuenta Railway | railway.app | ~$5 crédito/mes, luego uso | 10 min |
| Upstash Redis (opcional fase 2) | upstash.com | Gratis tier | 10 min |
| UptimeRobot | uptimerobot.com | Gratis | 10 min |
| Sentry | sentry.io | Gratis tier | 15 min |
| Meta Developers | Redirect prod OAuth | Gratis | 10 min |
| Supabase URLs prod | Dashboard Auth | Incluido | 10 min |

**Tiempo total tu parte (Fases 2–5):** 3–5 horas repartidas en 2 sesiones.

---

## Estimación de tiempo total (honesta)

| Fase | Dev (yo/agente) | Tú |
|------|-----------------|-----|
| 1 Preparación | ✅ 2–3 h | 0 |
| 2 Railway API | 1–2 h | 30 min cuentas + env vars |
| 3 Vercel Web | 1 h | 20 min DNS + env |
| 4 Supabase RLS | 2–3 h | 30 min revisar policies |
| 5 DNS + SSL | 30 min | 1 h propagación DNS |
| 6 Smoke tests | 2 h | 1 h pruebas manuales |
| 7 Monitoreo | 1 h | 30 min cuentas |

**Total:** ~10–14 h trabajo técnico + **4–6 h tuyas** → **2–4 días** calendario real.

---

## Fase 2 — Railway (próximo paso)

1. Push repo a GitHub
2. Railway → New Project → Deploy from GitHub
3. Root: repo root; Dockerfile path: `apps/api/Dockerfile`
4. Variables: copiar de `.env.production.example`
5. Dominio custom: `api.tudominio.com` → CNAME Railway
6. Validar: `curl https://api.tudominio.com/health`

---

## Fase 3 — Vercel (después de API)

1. Import repo → Framework Next.js
2. Root Directory: `apps/web` **o** usar `vercel.json` en raíz
3. Env: `NEXT_PUBLIC_*` + `SUPER_ADMIN_EMAILS`
4. Dominio: `app.tudominio.com` o apex
5. Validar login + dashboard + voz

---

## Fase 4 — Supabase producción

- Site URL = `WEB_PUBLIC_URL`
- Redirect URLs incluyen `/auth/callback`
- RLS en: `profiles`, `meta_connections`, `detected_leads`, `cognitive_memories`, `ced_activity_logs`, conversaciones, usage
- Backups: activar en plan Pro

---

## Fase 6 — Smoke tests prod

- [ ] Registro / login
- [ ] Voz Gemini Live (mic)
- [ ] Búsqueda web Tavily
- [ ] Conectar Instagram OAuth
- [ ] Prospección ON/OFF
- [ ] Stripe checkout test
- [ ] Webhook Stripe (Stripe CLI o dashboard)
- [ ] Mobile PWA básico

---

## Fase 7 — Monitoreo

- UptimeRobot: `GET /health` cada 5 min
- Sentry: DSN en API + Web (fase 7)
- Alertas Railway usage budget

---

## Contacto Meta / Google en prod

- **Meta redirect:** `https://api.TUDOMINIO/v1/meta/oauth/callback`
- **Google API key:** restringir por HTTP referrer (dominio Vercel) o IP Railway
