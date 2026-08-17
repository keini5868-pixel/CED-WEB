-- Estructura PM: ficha de cada socio (correo, nombre completo, ID de CED).
-- Permite apuntar invitados antes de que creen cuenta CED.
-- RLS deny-all: solo service_role vía API CED.

create table if not exists public.pm_structure_partners (
  id uuid primary key default gen_random_uuid(),
  sponsor_id uuid not null references public.profiles (id) on delete cascade,
  full_name text not null,
  email text not null,
  sponsor_ced_id text not null,
  user_id uuid references public.profiles (id) on delete set null,
  partner_ced_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint pm_structure_partners_email_uidx unique (sponsor_id, email)
);

create index if not exists pm_structure_partners_sponsor_idx
  on public.pm_structure_partners (sponsor_id, created_at desc);

create index if not exists pm_structure_partners_user_idx
  on public.pm_structure_partners (user_id)
  where user_id is not null;

alter table public.pm_structure_partners enable row level security;

drop policy if exists pm_structure_partners_service_only on public.pm_structure_partners;
create policy pm_structure_partners_service_only on public.pm_structure_partners
  for all using (false) with check (false);

comment on table public.pm_structure_partners is
  'Socios de Estructura PM: nombre, correo e ID de CED por patrocinador.';
