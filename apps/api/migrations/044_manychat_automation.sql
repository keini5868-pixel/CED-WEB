-- 044 — Automatización Instagram DM vía ManyChat (cerebro CED por usuario)

create table if not exists public.manychat_accounts (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  webhook_secret text not null,
  enabled boolean not null default false,
  role text not null default 'closer',
  tone text not null default 'cercano',
  mission text not null default '',
  ask_lines text not null default '',
  objections text not null default '',
  never_say text not null default '',
  cta_when text not null default 'ready',
  cta_url text not null default '',
  cta_label text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_manychat_accounts_secret
  on public.manychat_accounts (webhook_secret);

create table if not exists public.manychat_contacts (
  user_id uuid not null references public.profiles (id) on delete cascade,
  subscriber_id text not null,
  conversation_id text not null default '',
  display_name text not null default '',
  last_text text not null default '',
  updated_at timestamptz not null default now(),
  primary key (user_id, subscriber_id)
);

create table if not exists public.manychat_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  subscriber_id text not null default '',
  direction text not null default 'in',
  body text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists idx_manychat_messages_user
  on public.manychat_messages (user_id, created_at desc);

alter table public.manychat_accounts enable row level security;
alter table public.manychat_contacts enable row level security;
alter table public.manychat_messages enable row level security;

drop policy if exists manychat_accounts_service_only on public.manychat_accounts;
create policy manychat_accounts_service_only on public.manychat_accounts
  for all using (false) with check (false);

drop policy if exists manychat_contacts_service_only on public.manychat_contacts;
create policy manychat_contacts_service_only on public.manychat_contacts
  for all using (false) with check (false);

drop policy if exists manychat_messages_service_only on public.manychat_messages;
create policy manychat_messages_service_only on public.manychat_messages
  for all using (false) with check (false);
