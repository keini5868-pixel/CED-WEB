-- 006 — Gestión manual de usuarios (admin)

-- Rol co-admin opcional
alter table public.profiles drop constraint if exists profiles_role_check;
alter table public.profiles add constraint profiles_role_check
  check (role in ('client', 'super_admin', 'coadmin'));

alter table public.profiles add column if not exists phone text;
alter table public.profiles add column if not exists admin_notes text;

-- Extender suscripciones
alter table public.subscriptions add column if not exists access_type text
  not null default 'paid'
  check (access_type in ('paid', 'beta', 'founding_gift', 'coadmin'));

alter table public.subscriptions add column if not exists expires_at timestamptz;
alter table public.subscriptions add column if not exists created_by uuid references public.profiles (id);
alter table public.subscriptions add column if not exists admin_notes text;
alter table public.subscriptions add column if not exists paused_at timestamptz;
alter table public.subscriptions add column if not exists cancelled_at timestamptz;
alter table public.subscriptions add column if not exists updated_at timestamptz default now();

create unique index if not exists idx_subscriptions_user_unique
  on public.subscriptions (user_id);

create index if not exists idx_subscriptions_expires
  on public.subscriptions (expires_at)
  where expires_at is not null;

-- Límites diarios personalizados
create table if not exists public.usage_limits (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  minutes_daily int not null default 120 check (minutes_daily > 0 and minutes_daily <= 480),
  custom_limits jsonb default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Ampliar tipos de transacción
alter table public.transactions drop constraint if exists transactions_type_check;
alter table public.transactions add constraint transactions_type_check
  check (type in ('subscription', 'recharge', 'refund', 'admin_grant'));

alter table public.admin_audit_logs add column if not exists user_agent text;

create index if not exists idx_admin_audit_admin_created
  on public.admin_audit_logs (admin_user_id, created_at desc);

create index if not exists idx_admin_audit_target
  on public.admin_audit_logs (target_user_id, created_at desc);

create index if not exists idx_profiles_email_lower
  on public.profiles (lower(email));

-- RLS (service role bypass; usuarios solo leen lo propio)
alter table public.usage_limits enable row level security;

drop policy if exists usage_limits_select_own on public.usage_limits;
create policy usage_limits_select_own on public.usage_limits
  for select using (auth.uid() = user_id);
