-- 008 — Chat de texto (canal separado de voz)

alter table public.voice_conversations
  add column if not exists channel text not null default 'voice'
  check (channel in ('voice', 'text'));

create index if not exists idx_voice_conversations_user_channel
  on public.voice_conversations (user_id, channel, updated_at desc);
