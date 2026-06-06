-- Castillo Digital — esquema inicial (Supabase PostgreSQL)
-- Producto único: CED Élite (founding $149 / regular $249)

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  full_name text,
  role text not null default 'client' check (role in ('client', 'super_admin')),
  timezone text not null default 'America/Mexico_City',
  is_founding_member boolean not null default false,
  founding_slot_number integer,
  price_locked_usd integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  plan_id text not null check (plan_id in ('elite_founding', 'elite_regular')),
  stripe_customer_id text,
  stripe_subscription_id text,
  status text not null default 'trialing',
  trial_ends_at timestamptz,
  current_period_end timestamptz,
  price_locked_for_life boolean not null default false,
  created_at timestamptz not null default now()
);

-- Contador global founding (máx 50)
create table if not exists public.founding_registry (
  id integer primary key default 1 check (id = 1),
  slots_used integer not null default 0,
  slots_max integer not null default 50,
  updated_at timestamptz not null default now()
);

insert into public.founding_registry (id, slots_used, slots_max)
values (1, 0, 50)
on conflict (id) do nothing;

-- Uso diario Gemini Live
create table if not exists public.usage_logs (
  id bigserial primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  usage_date date not null,
  minutes_consumed numeric(10, 2) not null default 0,
  source text not null default 'gemini_live',
  session_id text,
  created_at timestamptz not null default now()
);

create index if not exists idx_usage_logs_user_date
  on public.usage_logs (user_id, usage_date);

-- Saldo de recargas flexible (NO expira)
create table if not exists public.recharge_balances (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  balance_usd numeric(12, 2) not null default 0,
  updated_at timestamptz not null default now()
);

-- Historial de cada recarga comprada
create table if not exists public.recharges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  amount_paid_usd numeric(10, 2) not null,
  client_balance_usd numeric(10, 2) not null,
  margin_keini_usd numeric(10, 2) not null,
  estimated_hours numeric(10, 2),
  stripe_payment_intent_id text,
  created_at timestamptz not null default now()
);

create table if not exists public.transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (id) on delete set null,
  type text not null check (type in ('subscription', 'recharge', 'refund')),
  amount_usd numeric(10, 2) not null,
  stripe_event_id text,
  metadata jsonb default '{}',
  created_at timestamptz not null default now()
);

create table if not exists public.admin_audit_logs (
  id bigserial primary key,
  admin_user_id uuid not null references public.profiles (id),
  action text not null,
  target_user_id uuid,
  payload jsonb default '{}',
  ip_address text,
  created_at timestamptz not null default now()
);
