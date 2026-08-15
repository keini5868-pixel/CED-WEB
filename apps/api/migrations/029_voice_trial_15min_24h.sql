-- Trial de producto: 7 días (imágenes/PDF Élite) desde el registro.
-- Voz: 15 min; el reloj de 24 h arranca en el primer uso (voice_trial_started_at).
-- Usuarios ya en trial de 7 días × 5 min/día no se tocan.

alter table public.subscriptions
  add column if not exists voice_trial_started_at timestamptz;

alter table public.subscriptions
  add column if not exists voice_trial_armed boolean not null default false;

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
      user_id, plan_id, status, trial_ends_at, access_type,
      voice_trial_armed, voice_trial_started_at
    )
    values (
      new.id,
      'elite',
      'trialing',
      now() + interval '7 days',
      'paid',
      true,
      null
    )
    on conflict (user_id) do nothing;

    insert into public.usage_limits (user_id, minutes_daily)
    values (new.id, 15)
    on conflict (user_id) do nothing;

    insert into public.recharge_balances (user_id, balance_usd)
    values (new.id, 0)
    on conflict (user_id) do nothing;
  end if;

  return new;
end;
$$;
