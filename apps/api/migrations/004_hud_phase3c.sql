-- Fase 3C — datos HUD: Instagram, leads, activity logs, perfil nicho

alter table public.profiles
  add column if not exists niche text,
  add column if not exists news_keywords text,
  add column if not exists prospection_enabled boolean not null default false;

create table if not exists public.meta_connections (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  ig_user_id text,
  ig_username text,
  page_id text,
  access_token text,
  followers_count integer,
  media_count integer,
  engagement_rate numeric(6, 2),
  last_post_at timestamptz,
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.detected_leads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  handle text not null,
  platform text not null default 'instagram',
  score integer not null default 50 check (score between 0 and 100),
  is_hot boolean not null default false,
  intent text,
  detected_at timestamptz not null default now()
);

create index if not exists idx_detected_leads_user_day
  on public.detected_leads (user_id, detected_at desc);

create table if not exists public.ced_activity_logs (
  id bigserial primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  action text not null,
  detail text,
  meta jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_ced_activity_user_created
  on public.ced_activity_logs (user_id, created_at desc);
