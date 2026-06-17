-- 014 — Chat de soporte usuario ↔ admin

create table if not exists public.support_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  category text not null check (category in ('bug', 'idea', 'question', 'other')),
  status text not null default 'open' check (status in ('open', 'in_progress', 'resolved')),
  last_message_at timestamptz not null default now(),
  unread_by_admin boolean not null default true,
  unread_by_user boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_support_conversations_user
  on public.support_conversations (user_id, last_message_at desc);

create index if not exists idx_support_conversations_admin_list
  on public.support_conversations (status, category, unread_by_admin, last_message_at desc);

create table if not exists public.support_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.support_conversations (id) on delete cascade,
  sender_type text not null check (sender_type in ('user', 'admin')),
  sender_id uuid not null references public.profiles (id) on delete cascade,
  content text not null default '',
  attachments jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_support_messages_conversation
  on public.support_messages (conversation_id, created_at asc);

-- RLS: acceso vía service role (API). Cliente directo denegado.
alter table public.support_conversations enable row level security;
alter table public.support_messages enable row level security;

drop policy if exists support_conversations_service_only on public.support_conversations;
create policy support_conversations_service_only on public.support_conversations
  for all using (false) with check (false);

drop policy if exists support_messages_service_only on public.support_messages;
create policy support_messages_service_only on public.support_messages
  for all using (false) with check (false);

-- Storage bucket (ejecutar en Supabase Dashboard o CLI si aplica)
-- insert into storage.buckets (id, name, public) values ('support-attachments', 'support-attachments', false);
-- La API usa también disco local en data/support_attachments como fallback.
