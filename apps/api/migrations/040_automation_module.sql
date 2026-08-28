-- Automatización piloto — embudo IG/FB → WhatsApp (Fase 1).
-- Backend (service_role) bypasea RLS. Cliente anon: deny-all.

create table if not exists public.ced_automations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  channel text not null check (channel in ('instagram', 'facebook', 'whatsapp')),
  trigger_type text not null check (
    trigger_type in (
      'dm_new',
      'dm_keyword',
      'comment_keyword',
      'comment_any',
      'lead_form',
      'wa_first_contact',
      'wa_outside_hours',
      'wa_inactivity_followup',
      'wa_fitline_link_after_questions',
      'wa_hot_lead_notify',
      'nurture_day'
    )
  ),
  name text not null default 'Automatización',
  card_key text,
  trigger_config jsonb not null default '{}'::jsonb,
  condition jsonb,
  action_config jsonb not null default '{}'::jsonb,
  status text not null default 'paused' check (status in ('active', 'paused', 'draft')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_triggered_at timestamptz
);

create index if not exists ced_automations_user_status_idx
  on public.ced_automations (user_id, status, channel);

create index if not exists ced_automations_card_key_idx
  on public.ced_automations (user_id, card_key)
  where card_key is not null;

create table if not exists public.ced_leads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  contact_id text not null,
  display_name text,
  channel_origen text not null check (
    channel_origen in ('instagram', 'facebook', 'whatsapp', 'direct', 'unknown')
  ),
  etiqueta text not null default 'frio' check (etiqueta in ('frio', 'tibio', 'caliente')),
  historial jsonb not null default '[]'::jsonb,
  meta jsonb not null default '{}'::jsonb,
  last_contact_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, contact_id, channel_origen)
);

create index if not exists ced_leads_user_etiqueta_idx
  on public.ced_leads (user_id, etiqueta, last_contact_at desc);

create table if not exists public.ced_automation_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (id) on delete set null,
  automation_id uuid references public.ced_automations (id) on delete set null,
  channel text not null,
  event_type text not null,
  contact_id text,
  payload jsonb not null default '{}'::jsonb,
  matched boolean not null default false,
  dry_run boolean not null default true,
  action_result jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ced_automation_events_user_created_idx
  on public.ced_automation_events (user_id, created_at desc);

create index if not exists ced_automation_events_created_idx
  on public.ced_automation_events (created_at desc);

alter table public.ced_automations enable row level security;
alter table public.ced_leads enable row level security;
alter table public.ced_automation_events enable row level security;

drop policy if exists ced_automations_service_only on public.ced_automations;
create policy ced_automations_service_only on public.ced_automations
  for all using (false) with check (false);

drop policy if exists ced_leads_service_only on public.ced_leads;
create policy ced_leads_service_only on public.ced_leads
  for all using (false) with check (false);

drop policy if exists ced_automation_events_service_only on public.ced_automation_events;
create policy ced_automation_events_service_only on public.ced_automation_events
  for all using (false) with check (false);

comment on table public.ced_automations is
  'Reglas de automatización IG/FB/WA — motor conversacional CED (piloto).';
comment on table public.ced_leads is
  'CRM ligero de prospectos del embudo Automatización.';
comment on table public.ced_automation_events is
  'Log de triggers (incluye dry-run) para validar lógica antes de envíos reales.';
