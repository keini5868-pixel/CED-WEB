-- 041 — Memoria persistente estructurada por cliente (CRM corto, no historial).
-- Solo service role vía API CED (RLS deny-all).

create table if not exists public.ced_user_memory (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  display_name text,
  business_niche text,
  plan_interest text,
  last_topic text,
  objections text[] not null default '{}',
  preferred_tone text,
  last_conversation_at timestamptz,
  -- Señales de engagement (hot lead / enfriamiento)
  topic_hits jsonb not null default '{}'::jsonb,
  price_ask_count int not null default 0,
  hot_lead_flagged_at timestamptz,
  cooling_flagged_at timestamptz,
  cooling_days int not null default 0,
  -- Solo super-admin / memoria completa
  tech_decisions text[] not null default '{}',
  speaking_style_notes text,
  extras jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ced_user_memory_last_conv_idx
  on public.ced_user_memory (last_conversation_at desc nulls last);

create index if not exists ced_user_memory_hot_idx
  on public.ced_user_memory (hot_lead_flagged_at desc nulls last)
  where hot_lead_flagged_at is not null;

alter table public.ced_user_memory enable row level security;

drop policy if exists ced_user_memory_service_only on public.ced_user_memory;
create policy ced_user_memory_service_only on public.ced_user_memory
  for all using (false) with check (false);

comment on table public.ced_user_memory is
  'Perfil corto por cliente para continuidad entre sesiones. NUNCA inyectar historial completo al prompt.';
