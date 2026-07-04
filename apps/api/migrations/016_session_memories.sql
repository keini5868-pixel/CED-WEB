-- 016 — Memoria sesión a sesión (resumen Gemini al cerrar llamada/chat)

create table if not exists public.session_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  session_id text not null,
  summary text not null,
  topics text[] not null default '{}',
  tasks_executed text[] not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists idx_session_memories_user_date
  on public.session_memories (user_id, created_at desc);

create unique index if not exists idx_session_memories_session
  on public.session_memories (session_id);

comment on table public.session_memories is 'Resúmenes Gemini al cerrar sesión voz/chat para continuidad entre sesiones';

alter table public.session_memories enable row level security;

drop policy if exists session_memories_select_own on public.session_memories;
create policy session_memories_select_own on public.session_memories
  for select using (auth.uid() = user_id);

drop policy if exists session_memories_insert_own on public.session_memories;
create policy session_memories_insert_own on public.session_memories
  for insert with check (auth.uid() = user_id);

drop policy if exists session_memories_update_own on public.session_memories;
create policy session_memories_update_own on public.session_memories
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
