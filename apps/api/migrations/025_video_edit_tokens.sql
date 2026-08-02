-- 025 — Módulo Video Edit (piloto): saldo de tokens + ledger + jobs
-- Solo API (service_role). Clientes JWT no leen ni escriben.

create table if not exists public.video_edit_token_balances (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  tokens integer not null default 0 check (tokens >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists public.video_edit_token_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  delta_tokens integer not null,
  reason text not null default 'adjust',
  duration_sec integer,
  job_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists video_edit_token_ledger_user_created_idx
  on public.video_edit_token_ledger (user_id, created_at desc);

create table if not exists public.video_edit_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'queued'
    check (status in (
      'queued', 'planning', 'rendering', 'done', 'failed', 'dry_run'
    )),
  duration_sec numeric not null default 0,
  tokens_charged integer not null default 0,
  script text not null default '',
  timeline jsonb not null default '{}'::jsonb,
  result_url text,
  error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists video_edit_jobs_user_created_idx
  on public.video_edit_jobs (user_id, created_at desc);

alter table public.video_edit_token_balances enable row level security;
alter table public.video_edit_token_ledger enable row level security;
alter table public.video_edit_jobs enable row level security;

drop policy if exists video_edit_token_balances_service_only
  on public.video_edit_token_balances;
create policy video_edit_token_balances_service_only
  on public.video_edit_token_balances
  for all using (false) with check (false);

drop policy if exists video_edit_token_ledger_service_only
  on public.video_edit_token_ledger;
create policy video_edit_token_ledger_service_only
  on public.video_edit_token_ledger
  for all using (false) with check (false);

drop policy if exists video_edit_jobs_service_only on public.video_edit_jobs;
create policy video_edit_jobs_service_only on public.video_edit_jobs
  for all using (false) with check (false);

comment on table public.video_edit_token_balances is
  'Saldo de tokens Video Edit ($1=100 tokens, 1s=1 token); solo service_role';

-- Permitir tipo de transacción Stripe para packs de video
alter table public.transactions drop constraint if exists transactions_type_check;
alter table public.transactions add constraint transactions_type_check
  check (type in (
    'subscription', 'recharge', 'refund', 'admin_grant', 'video_edit_tokens'
  ));
