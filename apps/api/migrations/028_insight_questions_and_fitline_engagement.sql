-- Foro interno de preguntas/dudas (solo admin vía API CED).
-- Captura automática de preguntas con valor de usuarios a CED.

create table if not exists public.ced_insight_questions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (id) on delete set null,
  question text not null,
  channel text not null default 'chat'
    check (channel in ('chat', 'voice', 'finance', 'advanced', 'other')),
  tags text[] not null default '{}',
  priority text not null default 'normal'
    check (priority in ('low', 'normal', 'high')),
  status text not null default 'new'
    check (status in ('new', 'reviewed', 'archived')),
  assistant_preview text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ced_insight_questions_created_idx
  on public.ced_insight_questions (created_at desc);

create index if not exists ced_insight_questions_status_idx
  on public.ced_insight_questions (status, created_at desc);

create index if not exists ced_insight_questions_tags_idx
  on public.ced_insight_questions using gin (tags);

alter table public.ced_insight_questions enable row level security;

create policy ced_insight_questions_service_only on public.ced_insight_questions
  for all using (false) with check (false);

comment on table public.ced_insight_questions is
  'Preguntas/dudas importantes auto-capturadas para el admin (foro interno soporte).';

-- Contador de engagement FitLine / cierre estratégico (persistente).
create table if not exists public.ced_fitline_engagement (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  question_count int not null default 0,
  closer_offered boolean not null default false,
  updated_at timestamptz not null default now()
);

alter table public.ced_fitline_engagement enable row level security;

create policy ced_fitline_engagement_service_only on public.ced_fitline_engagement
  for all using (false) with check (false);

comment on table public.ced_fitline_engagement is
  'Cuenta preguntas PM/FitLine por usuario para disparar cierre tras N turnos.';
