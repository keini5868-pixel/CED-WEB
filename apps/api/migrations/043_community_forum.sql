-- 043 — Sala CED (foro de prompts / guiones / copies / ayuda)

create table if not exists public.community_profiles (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  token text not null default 'listo',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.community_posts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  room text not null check (room in ('prompts', 'guiones', 'copies', 'ayuda')),
  title text not null default '',
  body text not null,
  token text not null default 'listo',
  display_name text not null default 'Operador',
  reactions jsonb not null default '{}'::jsonb,
  hidden boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_community_posts_room
  on public.community_posts (room, hidden, created_at desc);

create table if not exists public.community_replies (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.community_posts (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  body text not null,
  token text not null default 'listo',
  display_name text not null default 'Operador',
  hidden boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_community_replies_post
  on public.community_replies (post_id, hidden, created_at asc);

create table if not exists public.community_reports (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.community_posts (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  reason text not null default 'report',
  created_at timestamptz not null default now()
);

alter table public.community_profiles enable row level security;
alter table public.community_posts enable row level security;
alter table public.community_replies enable row level security;
alter table public.community_reports enable row level security;

drop policy if exists community_profiles_service_only on public.community_profiles;
create policy community_profiles_service_only on public.community_profiles
  for all using (false) with check (false);

drop policy if exists community_posts_service_only on public.community_posts;
create policy community_posts_service_only on public.community_posts
  for all using (false) with check (false);

drop policy if exists community_replies_service_only on public.community_replies;
create policy community_replies_service_only on public.community_replies
  for all using (false) with check (false);

drop policy if exists community_reports_service_only on public.community_reports;
create policy community_reports_service_only on public.community_reports
  for all using (false) with check (false);
