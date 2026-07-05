-- Google OAuth tokens — Calendar y Gmail (servicio API only)

create table if not exists public.calendar_tokens (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  access_token text not null,
  refresh_token text,
  expires_at timestamptz,
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gmail_tokens (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  access_token text not null,
  refresh_token text,
  expires_at timestamptz,
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.calendar_tokens enable row level security;
alter table public.gmail_tokens enable row level security;

create policy calendar_tokens_service_only on public.calendar_tokens
  for all using (false) with check (false);

create policy gmail_tokens_service_only on public.gmail_tokens
  for all using (false) with check (false);

comment on table public.calendar_tokens is 'OAuth Google Calendar — solo service_role';
comment on table public.gmail_tokens is 'OAuth Google Gmail — solo service_role';
