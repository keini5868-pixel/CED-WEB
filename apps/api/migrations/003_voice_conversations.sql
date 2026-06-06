-- Fase 2B — historial de voz + sesiones activas

create table if not exists public.voice_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  title text not null default 'Conversación CED',
  gemini_session_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_voice_conversations_user
  on public.voice_conversations (user_id, updated_at desc);

create table if not exists public.voice_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.voice_conversations (id) on delete cascade,
  role text not null check (role in ('user', 'model', 'system')),
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_voice_messages_conversation
  on public.voice_messages (conversation_id, created_at);

-- Agregado diario por sesión (evita duplicar filas por tick)
create unique index if not exists idx_usage_logs_user_date_session
  on public.usage_logs (user_id, usage_date, session_id)
  where session_id is not null;
