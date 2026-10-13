-- 046 — Sentinel Privacy (producto aparte de suscripción CED)

create table if not exists public.sentinel_privacy_subscriptions (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  plan_id text not null check (
    plan_id in ('sentinel_solo', 'sentinel_pro', 'sentinel_business')
  ),
  status text not null default 'active',
  stripe_subscription_id text,
  seals_per_month integer not null default 10 check (seals_per_month > 0),
  seals_used_in_period integer not null default 0 check (seals_used_in_period >= 0),
  period_start timestamptz,
  period_end timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists sentinel_privacy_sub_status_idx
  on public.sentinel_privacy_subscriptions (status);

alter table public.sentinel_privacy_subscriptions enable row level security;

drop policy if exists sentinel_privacy_sub_select_own on public.sentinel_privacy_subscriptions;
create policy sentinel_privacy_sub_select_own on public.sentinel_privacy_subscriptions
  for select using (auth.uid() = user_id);

comment on table public.sentinel_privacy_subscriptions is
  'Suscripción Sentinel Privacy — sellos ZK aparte del plan CED (Jarvis/chat)';

alter table public.transactions drop constraint if exists transactions_type_check;
alter table public.transactions add constraint transactions_type_check
  check (type in (
    'subscription', 'recharge', 'refund', 'admin_grant', 'video_edit_tokens',
    'sentinel_privacy'
  ));
