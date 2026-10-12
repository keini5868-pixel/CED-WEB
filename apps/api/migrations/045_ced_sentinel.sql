-- 045 — Centinela: guardia del super admin (estado + bitácora).
-- Solo el API con service_role lee y escribe. El panel admin no toca estas tablas directo.

create table if not exists public.ced_sentinel_state (
  id text primary key,
  enabled boolean not null default false,
  enabled_at timestamptz,
  checked_at timestamptz,
  checks jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.ced_sentinel_events (
  id uuid primary key,
  created_at timestamptz not null default now(),
  kind text not null,
  area text not null,
  level text not null,
  title text not null,
  detail text not null default '',
  latency_ms integer
);

create index if not exists idx_ced_sentinel_events_created
  on public.ced_sentinel_events (created_at desc);

alter table public.ced_sentinel_state enable row level security;
alter table public.ced_sentinel_events enable row level security;

drop policy if exists ced_sentinel_state_service_only on public.ced_sentinel_state;
create policy ced_sentinel_state_service_only on public.ced_sentinel_state
  for all using (false) with check (false);

drop policy if exists ced_sentinel_events_service_only on public.ced_sentinel_events;
create policy ced_sentinel_events_service_only on public.ced_sentinel_events
  for all using (false) with check (false);
