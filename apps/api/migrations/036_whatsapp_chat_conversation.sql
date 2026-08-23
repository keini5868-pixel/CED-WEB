-- Store CED chat conversation_id per WhatsApp contact (optional).
alter table public.whatsapp_contacts
  add column if not exists conversation_id uuid;
