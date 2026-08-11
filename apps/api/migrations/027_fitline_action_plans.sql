-- FitLine: enlace de patrocinio por usuario + plan de acción de franquicia.
-- El plan vive en Oportunidades (no en finance_transactions).

alter table public.profiles
  add column if not exists fitline_sponsor_url text;

comment on column public.profiles.fitline_sponsor_url is
  'Enlace de patrocinio FitLine/PM del usuario. Si vacío, se usa OPPORTUNITIES_FITLINE_SPONSOR_URL.';

create table if not exists public.fitline_action_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  title text not null default 'Plan de crecimiento de mi franquicia',
  status text not null default 'active'
    check (status in ('active', 'done', 'archived')),
  content jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists fitline_action_plans_user_updated_idx
  on public.fitline_action_plans (user_id, updated_at desc);

create unique index if not exists fitline_action_plans_one_active_per_user
  on public.fitline_action_plans (user_id)
  where status = 'active';

alter table public.fitline_action_plans enable row level security;

create policy fitline_action_plans_service_only on public.fitline_action_plans
  for all using (false) with check (false);

comment on table public.fitline_action_plans is
  'Plan de acción / crecimiento de franquicia FitLine — solo service_role vía API CED';
