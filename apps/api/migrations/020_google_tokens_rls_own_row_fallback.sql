-- Alternativa si SUPABASE_SERVICE_ROLE_KEY no está en Railway (no recomendado en prod).
-- Preferir service_role: el callback OAuth no tiene sesión de usuario; RLS own-row
-- solo ayuda si el cliente guarda tokens con JWT del usuario.
-- Ejecutar en Supabase SQL Editor solo si oauth_token_storage_ready=false en /v1/auth/diagnostics.

drop policy if exists calendar_tokens_service_only on public.calendar_tokens;
drop policy if exists gmail_tokens_service_only on public.gmail_tokens;

create policy allow_insert_own on public.calendar_tokens
  for all
  using (auth.uid()::text = user_id::text)
  with check (auth.uid()::text = user_id::text);

create policy allow_insert_own on public.gmail_tokens
  for all
  using (auth.uid()::text = user_id::text)
  with check (auth.uid()::text = user_id::text);

comment on table public.calendar_tokens is 'OAuth Google Calendar — service_role o RLS own-row';
comment on table public.gmail_tokens is 'OAuth Google Gmail — service_role o RLS own-row';
