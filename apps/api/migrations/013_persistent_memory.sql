-- 013 — Memoria persistente: mensajes, resúmenes de sesión, memoria a largo plazo

create extension if not exists vector;

create table if not exists public.user_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  session_id uuid not null,
  channel text not null check (channel in ('voice', 'text', 'mixed')),
  role text not null check (role in ('user', 'assistant', 'model', 'system')),
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(1536),
  created_at timestamptz not null default now()
);

create index if not exists idx_user_conversations_user_date
  on public.user_conversations (user_id, created_at desc);

create index if not exists idx_user_conversations_session
  on public.user_conversations (session_id, created_at);

create index if not exists idx_user_conversations_content_fts
  on public.user_conversations using gin (to_tsvector('spanish', coalesce(content, '')));

create table if not exists public.session_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  session_id uuid not null unique,
  summary text not null,
  topics text[] not null default '{}',
  key_facts jsonb not null default '{}'::jsonb,
  pending_actions text[] not null default '{}',
  channel text not null check (channel in ('voice', 'text', 'mixed')),
  duration_minutes numeric(10, 2),
  started_at timestamptz not null,
  ended_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_session_summaries_user_date
  on public.session_summaries (user_id, started_at desc);

create table if not exists public.long_term_memory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  category text not null,
  mem_key text not null,
  value text not null,
  importance int not null default 5 check (importance between 1 and 10),
  source_session_id uuid,
  embedding vector(1536),
  last_accessed_at timestamptz not null default now(),
  access_count int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, mem_key)
);

create index if not exists idx_long_term_memory_user_importance
  on public.long_term_memory (user_id, importance desc, updated_at desc);

comment on table public.user_conversations is 'Log unificado de mensajes CED (voz + chat)';
comment on table public.session_summaries is 'Resúmenes al cerrar sesión de voz/chat';
comment on table public.long_term_memory is 'Memoria a largo plazo categorizada';
