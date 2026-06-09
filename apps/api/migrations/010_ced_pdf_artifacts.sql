-- PDFs generados por CED (persistencia entre reinicios e instancias Railway)

create table if not exists public.ced_pdf_artifacts (
  file_id text primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  conversation_id uuid references public.voice_conversations (id) on delete set null,
  title text not null,
  filename text not null,
  pdf_base64 text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_ced_pdf_artifacts_user_created
  on public.ced_pdf_artifacts (user_id, created_at desc);
