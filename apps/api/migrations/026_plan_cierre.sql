-- 026 — Plan CED Cierre ($20/mes, foco PM International / FitLine)

alter table public.subscriptions drop constraint if exists subscriptions_plan_id_check;
alter table public.subscriptions add constraint subscriptions_plan_id_check
  check (plan_id in (
    'cierre', 'starter', 'pro', 'elite', 'founding', 'free_basic',
    'elite_founding', 'elite_regular'
  ));
