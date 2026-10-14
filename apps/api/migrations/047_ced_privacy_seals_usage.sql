-- 047 — Uso unificado de sellos (plan CED incluido + Sentinel volumen)

alter table public.subscriptions
  add column if not exists privacy_seals_used_in_period integer not null default 0
  check (privacy_seals_used_in_period >= 0);

comment on column public.subscriptions.privacy_seals_used_in_period is
  'Sellos consumidos en el periodo de facturación CED (pool compartido con cupo Sentinel)';
