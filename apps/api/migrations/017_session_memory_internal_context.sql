-- 017 — Memoria de sesión: resumen público corto + contexto interno rico (solo LLM)

alter table public.session_memories
  add column if not exists internal_context text;

alter table public.session_memories
  add column if not exists projects text[] not null default '{}';

alter table public.session_memories
  add column if not exists user_context jsonb not null default '{}'::jsonb;

comment on column public.session_memories.summary is 'Resumen corto y natural para saludo (nunca transcript user:/assistant:)';
comment on column public.session_memories.internal_context is 'Memoria rica inyectada al LLM — no mostrar al usuario';
