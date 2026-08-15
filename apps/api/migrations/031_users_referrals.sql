-- Referidos CED: cada socio tiene un Referral ID; ve actividad de venta de sus invitados.
-- RLS deny-all: solo service_role vía API CED (no filtrar PII por el cliente).

alter table public.profiles
  add column if not exists referral_code text;

create unique index if not exists profiles_referral_code_uidx
  on public.profiles (referral_code)
  where referral_code is not null;

comment on column public.profiles.referral_code is
  'Referral ID público del socio (p. ej. CED7A3F2C). Se genera al primer uso.';

create table if not exists public.users_referrals (
  id uuid primary key default gen_random_uuid(),
  referrer_id uuid not null references public.profiles (id) on delete cascade,
  referred_id uuid not null references public.profiles (id) on delete cascade,
  referral_code text not null,
  created_at timestamptz not null default now(),
  constraint users_referrals_referred_unique unique (referred_id),
  constraint users_referrals_no_self check (referrer_id <> referred_id)
);

create index if not exists users_referrals_referrer_idx
  on public.users_referrals (referrer_id, created_at desc);

alter table public.users_referrals enable row level security;

drop policy if exists users_referrals_service_only on public.users_referrals;
create policy users_referrals_service_only on public.users_referrals
  for all using (false) with check (false);

comment on table public.users_referrals is
  'Vínculo referidor → invitado. Un invitado solo puede tener un referidor.';

create table if not exists public.referral_activity_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  kind text not null
    check (kind in (
      'voice',
      'voice_pm',
      'chat_sales',
      'finance',
      'opps',
      'sponsor'
    )),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists referral_activity_user_kind_idx
  on public.referral_activity_events (user_id, kind, created_at desc);

alter table public.referral_activity_events enable row level security;

drop policy if exists referral_activity_events_service_only
  on public.referral_activity_events;
create policy referral_activity_events_service_only
  on public.referral_activity_events
  for all using (false) with check (false);

comment on table public.referral_activity_events is
  'Señales de actividad relevante para el dashboard Mis Invitados (venta PM/FitLine).';
