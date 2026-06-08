-- 007 — Modelo de negocio: 4 planes + trial 7d + plan básico gratis

-- Ampliar plan_id en suscripciones
alter table public.subscriptions drop constraint if exists subscriptions_plan_id_check;
alter table public.subscriptions add constraint subscriptions_plan_id_check
  check (plan_id in (
    'starter', 'pro', 'elite', 'founding', 'free_basic',
    'elite_founding', 'elite_regular'
  ));

-- Permitir 0 minutos (plan básico gratis)
alter table public.usage_limits drop constraint if exists usage_limits_minutes_daily_check;
alter table public.usage_limits add constraint usage_limits_minutes_daily_check
  check (minutes_daily >= 0 and minutes_daily <= 9999);

-- Trial automático al registrarse (7 días premium)
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  admin_emails text[];
  assigned_role text := 'client';
begin
  admin_emails := string_to_array(
    coalesce(current_setting('app.super_admin_emails', true), ''),
    ','
  );

  if new.email is not null and lower(new.email) = any (
    select lower(trim(e)) from unnest(admin_emails) as e where trim(e) <> ''
  ) then
    assigned_role := 'super_admin';
  end if;

  insert into public.profiles (id, email, full_name, role)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data->>'full_name', ''),
    assigned_role
  )
  on conflict (id) do update set
    email = excluded.email,
    full_name = coalesce(excluded.full_name, profiles.full_name),
    updated_at = now();

  if assigned_role = 'client' then
    insert into public.subscriptions (
      user_id, plan_id, status, trial_ends_at, access_type
    )
    values (
      new.id,
      'elite',
      'trialing',
      now() + interval '7 days',
      'paid'
    )
    on conflict (user_id) do nothing;

    insert into public.usage_limits (user_id, minutes_daily)
    values (new.id, 30)
    on conflict (user_id) do nothing;

    insert into public.recharge_balances (user_id, balance_usd)
    values (new.id, 0)
    on conflict (user_id) do nothing;
  end if;

  return new;
end;
$$;
