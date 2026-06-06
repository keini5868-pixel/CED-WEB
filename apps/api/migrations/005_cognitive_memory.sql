-- Memoria cognitiva persistente por usuario (Fase 4 web)

create table if not exists public.cognitive_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  mem_key text not null,
  content text not null,
  category text,
  tags text[] default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, mem_key)
);

create index if not exists idx_cognitive_memories_user
  on public.cognitive_memories (user_id, updated_at desc);

create index if not exists idx_cognitive_memories_search
  on public.cognitive_memories using gin (to_tsvector('spanish', coalesce(content, '') || ' ' || coalesce(mem_key, '')));
