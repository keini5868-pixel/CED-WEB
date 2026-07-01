-- 015 — Seguridad crítica: RLS en todas las tablas public
-- Backend (service_role) bypasea RLS. Cliente anon/authenticated respeta políticas.
-- Tablas con tokens/secretos: deny-all (solo service_role).

-- ─── Perfiles (frontend lee role vía anon+JWT) ───────────────────────────────
alter table public.profiles enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
  for select using (auth.uid() = id);

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
  for update using (auth.uid() = id)
  with check (auth.uid() = id);

-- ─── Suscripciones y billing ─────────────────────────────────────────────────
alter table public.subscriptions enable row level security;

drop policy if exists subscriptions_select_own on public.subscriptions;
create policy subscriptions_select_own on public.subscriptions
  for select using (auth.uid() = user_id);

-- founding_registry: solo backend (contador founding)
alter table public.founding_registry enable row level security;

drop policy if exists founding_registry_service_only on public.founding_registry;
create policy founding_registry_service_only on public.founding_registry
  for all using (false) with check (false);

alter table public.usage_logs enable row level security;

drop policy if exists usage_logs_select_own on public.usage_logs;
create policy usage_logs_select_own on public.usage_logs
  for select using (auth.uid() = user_id);

drop policy if exists usage_logs_insert_own on public.usage_logs;
create policy usage_logs_insert_own on public.usage_logs
  for insert with check (auth.uid() = user_id);

alter table public.recharge_balances enable row level security;

drop policy if exists recharge_balances_select_own on public.recharge_balances;
create policy recharge_balances_select_own on public.recharge_balances
  for select using (auth.uid() = user_id);

alter table public.recharges enable row level security;

drop policy if exists recharges_select_own on public.recharges;
create policy recharges_select_own on public.recharges
  for select using (auth.uid() = user_id);

alter table public.transactions enable row level security;

drop policy if exists transactions_select_own on public.transactions;
create policy transactions_select_own on public.transactions
  for select using (auth.uid() = user_id);

-- ─── Admin / auditoría — solo service_role ───────────────────────────────────
alter table public.admin_audit_logs enable row level security;

drop policy if exists admin_audit_logs_service_only on public.admin_audit_logs;
create policy admin_audit_logs_service_only on public.admin_audit_logs
  for all using (false) with check (false);

-- ─── Voz y chat ──────────────────────────────────────────────────────────────
alter table public.voice_conversations enable row level security;

drop policy if exists voice_conversations_select_own on public.voice_conversations;
create policy voice_conversations_select_own on public.voice_conversations
  for select using (auth.uid() = user_id);

drop policy if exists voice_conversations_insert_own on public.voice_conversations;
create policy voice_conversations_insert_own on public.voice_conversations
  for insert with check (auth.uid() = user_id);

drop policy if exists voice_conversations_update_own on public.voice_conversations;
create policy voice_conversations_update_own on public.voice_conversations
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists voice_conversations_delete_own on public.voice_conversations;
create policy voice_conversations_delete_own on public.voice_conversations
  for delete using (auth.uid() = user_id);

alter table public.voice_messages enable row level security;

drop policy if exists voice_messages_select_own on public.voice_messages;
create policy voice_messages_select_own on public.voice_messages
  for select using (
    exists (
      select 1 from public.voice_conversations vc
      where vc.id = conversation_id and vc.user_id = auth.uid()
    )
  );

drop policy if exists voice_messages_insert_own on public.voice_messages;
create policy voice_messages_insert_own on public.voice_messages
  for insert with check (
    exists (
      select 1 from public.voice_conversations vc
      where vc.id = conversation_id and vc.user_id = auth.uid()
    )
  );

-- ─── Meta OAuth — access_token NUNCA expuesto al cliente ───────────────────
alter table public.meta_connections enable row level security;

drop policy if exists meta_connections_service_only on public.meta_connections;
create policy meta_connections_service_only on public.meta_connections
  for all using (false) with check (false);

alter table public.detected_leads enable row level security;

drop policy if exists detected_leads_select_own on public.detected_leads;
create policy detected_leads_select_own on public.detected_leads
  for select using (auth.uid() = user_id);

drop policy if exists detected_leads_insert_own on public.detected_leads;
create policy detected_leads_insert_own on public.detected_leads
  for insert with check (auth.uid() = user_id);

alter table public.ced_activity_logs enable row level security;

drop policy if exists ced_activity_logs_select_own on public.ced_activity_logs;
create policy ced_activity_logs_select_own on public.ced_activity_logs
  for select using (auth.uid() = user_id);

drop policy if exists ced_activity_logs_insert_own on public.ced_activity_logs;
create policy ced_activity_logs_insert_own on public.ced_activity_logs
  for insert with check (auth.uid() = user_id);

-- ─── Memoria cognitiva ───────────────────────────────────────────────────────
alter table public.cognitive_memories enable row level security;

drop policy if exists cognitive_memories_select_own on public.cognitive_memories;
create policy cognitive_memories_select_own on public.cognitive_memories
  for select using (auth.uid() = user_id);

drop policy if exists cognitive_memories_insert_own on public.cognitive_memories;
create policy cognitive_memories_insert_own on public.cognitive_memories
  for insert with check (auth.uid() = user_id);

drop policy if exists cognitive_memories_update_own on public.cognitive_memories;
create policy cognitive_memories_update_own on public.cognitive_memories
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists cognitive_memories_delete_own on public.cognitive_memories;
create policy cognitive_memories_delete_own on public.cognitive_memories
  for delete using (auth.uid() = user_id);

-- usage_limits (006) — completar políticas
alter table public.usage_limits enable row level security;

drop policy if exists usage_limits_select_own on public.usage_limits;
create policy usage_limits_select_own on public.usage_limits
  for select using (auth.uid() = user_id);

-- internal_knowledge_articles (009) — ya deny-all; reafirmar
alter table public.internal_knowledge_articles enable row level security;

drop policy if exists internal_knowledge_service_only on public.internal_knowledge_articles;
create policy internal_knowledge_service_only on public.internal_knowledge_articles
  for all using (false) with check (false);

-- PDFs — pdf_base64 solo vía API service_role
alter table public.ced_pdf_artifacts enable row level security;

drop policy if exists ced_pdf_artifacts_service_only on public.ced_pdf_artifacts;
create policy ced_pdf_artifacts_service_only on public.ced_pdf_artifacts
  for all using (false) with check (false);

alter table public.openai_usage_log enable row level security;

drop policy if exists openai_usage_log_select_own on public.openai_usage_log;
create policy openai_usage_log_select_own on public.openai_usage_log
  for select using (auth.uid() = user_id);

drop policy if exists openai_usage_log_service_write on public.openai_usage_log;
create policy openai_usage_log_service_write on public.openai_usage_log
  for insert with check (auth.uid() = user_id);

alter table public.generated_images enable row level security;

drop policy if exists generated_images_select_own on public.generated_images;
create policy generated_images_select_own on public.generated_images
  for select using (auth.uid() = user_id);

drop policy if exists generated_images_insert_own on public.generated_images;
create policy generated_images_insert_own on public.generated_images
  for insert with check (auth.uid() = user_id);

-- ─── Memoria persistente (013) ───────────────────────────────────────────────
alter table public.user_conversations enable row level security;

drop policy if exists user_conversations_select_own on public.user_conversations;
create policy user_conversations_select_own on public.user_conversations
  for select using (auth.uid() = user_id);

drop policy if exists user_conversations_insert_own on public.user_conversations;
create policy user_conversations_insert_own on public.user_conversations
  for insert with check (auth.uid() = user_id);

alter table public.session_summaries enable row level security;

drop policy if exists session_summaries_select_own on public.session_summaries;
create policy session_summaries_select_own on public.session_summaries
  for select using (auth.uid() = user_id);

drop policy if exists session_summaries_insert_own on public.session_summaries;
create policy session_summaries_insert_own on public.session_summaries
  for insert with check (auth.uid() = user_id);

drop policy if exists session_summaries_update_own on public.session_summaries;
create policy session_summaries_update_own on public.session_summaries
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

alter table public.long_term_memory enable row level security;

drop policy if exists long_term_memory_select_own on public.long_term_memory;
create policy long_term_memory_select_own on public.long_term_memory
  for select using (auth.uid() = user_id);

drop policy if exists long_term_memory_insert_own on public.long_term_memory;
create policy long_term_memory_insert_own on public.long_term_memory
  for insert with check (auth.uid() = user_id);

drop policy if exists long_term_memory_update_own on public.long_term_memory;
create policy long_term_memory_update_own on public.long_term_memory
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists long_term_memory_delete_own on public.long_term_memory;
create policy long_term_memory_delete_own on public.long_term_memory
  for delete using (auth.uid() = user_id);

-- support_* (014) — reafirmar deny-all
alter table public.support_conversations enable row level security;
alter table public.support_messages enable row level security;

drop policy if exists support_conversations_service_only on public.support_conversations;
create policy support_conversations_service_only on public.support_conversations
  for all using (false) with check (false);

drop policy if exists support_messages_service_only on public.support_messages;
create policy support_messages_service_only on public.support_messages
  for all using (false) with check (false);

comment on table public.meta_connections is
  'Tokens Meta OAuth — RLS deny-all; solo API con service_role';
