-- 011 — Migración OpenAI Realtime: tracking costos + imágenes generadas

create table if not exists public.openai_usage_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id text,
  event_type text not null default 'voice',
  model text,
  input_tokens int default 0,
  output_tokens int default 0,
  audio_seconds numeric(10,2) default 0,
  estimated_cost_usd numeric(12,6) default 0,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists openai_usage_log_user_created_idx
  on public.openai_usage_log (user_id, created_at desc);

create table if not exists public.generated_images (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  prompt text not null,
  quality text not null default 'standard',
  model text default 'gpt-image-1',
  storage_path text,
  public_url text,
  estimated_cost_usd numeric(12,6) default 0,
  created_at timestamptz not null default now()
);

create index if not exists generated_images_user_created_idx
  on public.generated_images (user_id, created_at desc);

-- Trial: 15 min voz/día (antes 30 en signup legacy)
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
    values (new.id, 15)
    on conflict (user_id) do nothing;

    insert into public.recharge_balances (user_id, balance_usd)
    values (new.id, 0)
    on conflict (user_id) do nothing;
  end if;

  return new;
end;
$$;

comment on table public.openai_usage_log is 'Tracking costos OpenAI Realtime por usuario';
comment on table public.generated_images is 'Imágenes GPT-Image-1 generadas por CED';
