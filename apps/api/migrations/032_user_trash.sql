-- Papelera de usuario: soft-delete con retención de 30 días.
-- Conversaciones, imágenes, PDFs y movimientos de finanzas.

alter table public.voice_conversations
  add column if not exists deleted_at timestamptz,
  add column if not exists purge_after timestamptz;

alter table public.generated_images
  add column if not exists deleted_at timestamptz,
  add column if not exists purge_after timestamptz;

alter table public.ced_pdf_artifacts
  add column if not exists deleted_at timestamptz,
  add column if not exists purge_after timestamptz;

alter table public.finance_transactions
  add column if not exists deleted_at timestamptz,
  add column if not exists purge_after timestamptz;

create index if not exists voice_conversations_user_trash_idx
  on public.voice_conversations (user_id, deleted_at)
  where deleted_at is not null;

create index if not exists generated_images_user_trash_idx
  on public.generated_images (user_id, deleted_at)
  where deleted_at is not null;

create index if not exists ced_pdf_artifacts_user_trash_idx
  on public.ced_pdf_artifacts (user_id, deleted_at)
  where deleted_at is not null;

create index if not exists finance_transactions_user_trash_idx
  on public.finance_transactions (user_id, deleted_at)
  where deleted_at is not null;

comment on column public.voice_conversations.deleted_at is
  'Soft-delete: en papelera hasta purge_after (30 días).';
comment on column public.finance_transactions.deleted_at is
  'Soft-delete: en papelera hasta purge_after (30 días).';
