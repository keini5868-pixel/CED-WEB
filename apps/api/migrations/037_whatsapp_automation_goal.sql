-- Objetivo de automatización por cuenta WhatsApp (multi-usuario).
alter table public.whatsapp_accounts
  add column if not exists automation_goal text not null default '';

alter table public.whatsapp_accounts
  add column if not exists automation_cta_url text not null default '';

alter table public.whatsapp_accounts
  add column if not exists automation_cta_label text not null default '';

comment on column public.whatsapp_accounts.automation_goal is
  'Qué acción debe perseguir CED en los chats inbound de este número.';
