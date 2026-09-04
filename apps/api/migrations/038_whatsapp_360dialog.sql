-- WhatsApp por 360dialog (BSP): provider + misma access_token = API key del canal.

alter table public.whatsapp_accounts
  add column if not exists provider text not null default 'meta';

comment on column public.whatsapp_accounts.provider is
  'meta = Cloud API directa; 360dialog = BSP (API key en access_token).';
