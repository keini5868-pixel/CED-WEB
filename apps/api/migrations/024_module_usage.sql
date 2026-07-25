-- 024 — Metering de módulos VIABLE / Tendencias / Oportunidades
-- Solo API (service_role). Clientes JWT no leen ni escriben.

create table if not exists public.module_usage (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  module text not null check (
    module in ('viability', 'trends', 'opportunities')
  ),
  plan_id text not null default 'unknown',
  plan_status text not null default 'unknown',
  channel text not null default 'http'
    check (channel in ('http', 'voice', 'chat', 'other')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists module_usage_user_created_idx
  on public.module_usage (user_id, created_at desc);

create index if not exists module_usage_module_created_idx
  on public.module_usage (module, created_at desc);

create index if not exists module_usage_plan_created_idx
  on public.module_usage (plan_id, created_at desc);

alter table public.module_usage enable row level security;

drop policy if exists module_usage_service_only on public.module_usage;
create policy module_usage_service_only on public.module_usage
  for all using (false) with check (false);

comment on table public.module_usage is
  'Metering VIABLE/Tendencias/Oportunidades — plan snapshot al momento de la consulta; solo service_role';
