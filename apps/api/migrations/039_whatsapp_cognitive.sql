-- ADN del prospecto + HUD de misión (WhatsApp).
-- Ejecutar en Supabase SQL editor.

alter table public.whatsapp_contacts
  add column if not exists prospect_dna text not null default 'Analítico';

alter table public.whatsapp_contacts
  add column if not exists sentiment text not null default 'neutro';

alter table public.whatsapp_contacts
  add column if not exists close_score int not null default 0;

alter table public.whatsapp_contacts
  add column if not exists leak_risk int not null default 0;

alter table public.whatsapp_contacts
  add column if not exists human_alert text not null default '';

comment on column public.whatsapp_contacts.prospect_dna is
  'Urgente | Analítico | Escéptico | Decidido';
comment on column public.whatsapp_contacts.close_score is
  'Probabilidad de cierre 0-100 para HUD de intervención';
