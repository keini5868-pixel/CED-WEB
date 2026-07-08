-- Finanzas personales — movimientos (ingresos/gastos) por usuario
-- Persistencia permanente para análisis y planes financieros de CED.

create table if not exists public.finance_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  type text not null check (type in ('ingreso', 'gasto')),
  amount numeric(12, 2) not null check (amount > 0),
  currency text not null default 'USD',
  category text,
  description text,
  occurred_on date not null default current_date,
  created_at timestamptz not null default now()
);

create index if not exists finance_transactions_user_date_idx
  on public.finance_transactions (user_id, occurred_on desc);

create index if not exists finance_transactions_user_type_idx
  on public.finance_transactions (user_id, type);

alter table public.finance_transactions enable row level security;

create policy finance_transactions_service_only on public.finance_transactions
  for all using (false) with check (false);

comment on table public.finance_transactions is 'Movimientos de finanzas personales CED — solo service_role';
