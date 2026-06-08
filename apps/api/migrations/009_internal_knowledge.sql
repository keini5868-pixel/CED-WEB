-- 009 — Cerebro interno CED (conocimiento enciclopédico por ramas)

create table if not exists public.internal_knowledge_articles (
  id uuid primary key default gen_random_uuid(),
  domain text not null,
  subdomain text,
  title text not null,
  summary text not null,
  keywords text[] not null default '{}',
  is_time_sensitive boolean not null default false,
  source text default 'ced_curated',
  locale text not null default 'es',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_internal_knowledge_domain
  on public.internal_knowledge_articles (domain);

create index if not exists idx_internal_knowledge_fts
  on public.internal_knowledge_articles
  using gin (to_tsvector('spanish', coalesce(title, '') || ' ' || coalesce(summary, '')));

alter table public.internal_knowledge_articles enable row level security;

-- Lectura pública vía service role (API backend); sin acceso directo cliente
create policy "internal_knowledge_service_only"
  on public.internal_knowledge_articles
  for all
  using (false)
  with check (false);

comment on table public.internal_knowledge_articles is
  'Base enciclopédica CED — expandir con ingest admin/Wikipedia curada';
