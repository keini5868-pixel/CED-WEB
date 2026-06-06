# Fase 1 — Completa

## URLs locales

| Página | URL |
|--------|-----|
| Landing | http://localhost:3000 |
| Signup | http://localhost:3000/signup |
| Login | http://localhost:3000/login |
| Recuperar contraseña | http://localhost:3000/forgot-password |
| Nueva contraseña (email) | http://localhost:3000/reset-password |
| Verificar email | http://localhost:3000/verify-email |
| Dashboard | http://localhost:3000/dashboard |
| Admin | http://localhost:3000/admin |

Alias: `/register` → `/signup`, `/app` → `/dashboard`

```powershell
cd C:\Users\keini\OneDrive\Escritorio\CED-WEB
pnpm dev:web
pnpm dev:api
```

## Super admin — Keini

1. Regístrate en **/signup** con **keini5868@gmail.com** (mismo que `SUPER_ADMIN_EMAILS`).
2. Si Supabase exige confirmación, abre el enlace del email o usa **/verify-email**.
3. Inicia sesión → **/dashboard** muestra **🏰 PANEL ADMIN**.
4. **/admin** solo accesible con ese rol.

Alternativas: `profiles.role = super_admin'` o `app_metadata.role` en Supabase.

## Supabase — Redirect URLs

En Authentication → URL Configuration:

- `http://localhost:3000/auth/callback`
- `http://localhost:3000/reset-password`
- `http://localhost:3000/dashboard`

## Qué probar

- [ ] Registro email/password
- [ ] Email de verificación (reenviar en /verify-email)
- [ ] Login y logout (SALIR)
- [ ] Recuperación: forgot → email → reset-password
- [ ] Google OAuth (si está activo)
- [ ] /dashboard sin login → redirige a /login
- [ ] Usuario normal no entra a /admin
- [ ] keini5868@gmail.com ve Panel Admin
- [ ] HUD móvil: paneles colapsables
- [ ] API: http://localhost:8000/v1/integrations

## Tablas SQL

Migración `001_initial_schema.sql` aplicada. Verificar:

```powershell
cd apps\api
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env'); from app.services.integrations import check_supabase; print(check_supabase())"
```

## Fase 2 — Gemini Live

1. Token efímero Gemini en API (sin exponer API key en web).
2. Orbe central con estados IDLE / escuchando / hablando.
3. WebRTC o SDK de voz en el panel central.
4. Contador de minutos desde `usage_logs`.
