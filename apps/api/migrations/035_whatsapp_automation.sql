-- WhatsApp Cloud API — cuenta por usuario, flujos y registro de mensajes.
-- Backend (service_role) bypasea RLS. Cliente anon: deny-all (tokens).

create table if not exists public.whatsapp_accounts (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  waba_id text,
  phone_number_id text not null,
  display_phone text,
  verified_name text,
  access_token text not null,
  token_expires_at timestamptz,
  status text not null default 'active',
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists whatsapp_accounts_phone_number_id_uidx
  on public.whatsapp_accounts (phone_number_id);

create table if not exists public.whatsapp_flows (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  name text not null default 'Flujo',
  trigger_type text not null default 'keyword',
  keywords text not null default '',
  reply_text text not null,
  enabled boolean not null default true,
  priority int not null default 100,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists whatsapp_flows_user_id_idx
  on public.whatsapp_flows (user_id, enabled, priority);

create table if not exists public.whatsapp_contacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  wa_from text not null,
  opted_out boolean not null default false,
  last_inbound_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, wa_from)
);

create table if not exists public.whatsapp_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  wamid text,
  direction text not null,
  wa_from text,
  wa_to text,
  body text,
  flow_id uuid references public.whatsapp_flows (id) on delete set null,
  raw jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists whatsapp_messages_wamid_uidx
  on public.whatsapp_messages (wamid)
  where wamid is not null;

create index if not exists whatsapp_messages_user_created_idx
  on public.whatsapp_messages (user_id, created_at desc);

alter table public.whatsapp_accounts enable row level security;
alter table public.whatsapp_flows enable row level security;
alter table public.whatsapp_contacts enable row level security;
alter table public.whatsapp_messages enable row level security;

drop policy if exists whatsapp_accounts_service_only on public.whatsapp_accounts;
create policy whatsapp_accounts_service_only on public.whatsapp_accounts
  for all using (false) with check (false);

drop policy if exists whatsapp_flows_service_only on public.whatsapp_flows;
create policy whatsapp_flows_service_only on public.whatsapp_flows
  for all using (false) with check (false);

drop policy if exists whatsapp_contacts_service_only on public.whatsapp_contacts;
create policy whatsapp_contacts_service_only on public.whatsapp_contacts
  for all using (false) with check (false);

drop policy if exists whatsapp_messages_service_only on public.whatsapp_messages;
create policy whatsapp_messages_service_only on public.whatsapp_messages
  for all using (false) with check (false);

comment on table public.whatsapp_accounts is 'WhatsApp Cloud API — token y phone_number_id por usuario CED';
comment on table public.whatsapp_flows is 'Auto-respuestas por palabra clave / catch-all';
comment on table public.whatsapp_messages is 'Registro inbound/outbound WhatsApp';
