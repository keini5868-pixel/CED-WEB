# Configuración de servicios — Fase 0

## 1. Supabase

1. Crear proyecto en https://supabase.com/dashboard  
2. **Authentication** → habilitar Email y Google OAuth  
3. **SQL Editor** → ejecutar `apps/api/migrations/001_initial_schema.sql`  
4. Copiar:
   - Project URL → `NEXT_PUBLIC_SUPABASE_URL` / `SUPABASE_URL`
   - anon key → `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - service_role → `SUPABASE_SERVICE_ROLE_KEY` (solo backend)
   - JWT Secret → `SUPABASE_JWT_SECRET`

## 2. Stripe (modo test)

1. https://dashboard.stripe.com/test/apikeys  
2. Crear **2** productos recurrentes:
   - CED Pro Founding — **$35/mes** (máx 50 clientes; contador en `founding_registry`)
   - CED Pro Regular — **$49/mes**
   - Incluye **45 min/día** voz; recargas flexibles si pasan el cupo
3. Copiar `price_...` IDs → `STRIPE_PRICE_ELITE_FOUNDING` y `STRIPE_PRICE_ELITE_REGULAR`
4. Recargas: productos one-time o Payment Intents dinámicos ($5–$500)  
4. Webhooks (Fase 7): endpoint `https://api.castillodigital.com/v1/billing/webhooks/stripe`  
5. Eventos: `checkout.session.completed`, `payment_intent.succeeded`, `customer.subscription.*`

## 3. Redis

- **Desarrollo:** Docker `redis:7` o Upstash free tier  
- URL → `REDIS_URL`

## 4. Vercel (Fase 1+)

1. Importar repo, root `apps/web`  
2. Variables `NEXT_PUBLIC_*` desde `.env.example`

## 5. Railway / Render (API)

1. Root `apps/api`, start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`  
2. Variables desde `apps/api/.env.example`

## 6. Resend

https://resend.com → API key → `RESEND_API_KEY`

## 7. Dominio (producción)

| Subdominio | Servicio |
|------------|----------|
| `ced.castillodigital.com` | Vercel |
| `api.castillodigital.com` | Railway |

## 8. API keys IA (solo backend)

- Google AI Studio → `GOOGLE_API_KEY` (Gemini Live)  
- Anthropic → `ANTHROPIC_API_KEY`  
- Tavily → `TAVILY_API_KEY` (búsqueda HUD)

**Nunca** prefijo `NEXT_PUBLIC_` en claves secretas.
