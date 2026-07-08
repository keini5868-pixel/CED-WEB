-- Finanzas: soporte para pagos pendientes/programados (compromisos a futuro)
-- status: 'pagado' (movimiento ya realizado) | 'pendiente' (compromiso futuro)
-- due_date: fecha de vencimiento del pago pendiente

alter table public.finance_transactions
  add column if not exists status text not null default 'pagado',
  add column if not exists due_date date;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'finance_transactions_status_check'
  ) then
    alter table public.finance_transactions
      add constraint finance_transactions_status_check
      check (status in ('pagado', 'pendiente'));
  end if;
end $$;

create index if not exists finance_transactions_user_status_due_idx
  on public.finance_transactions (user_id, status, due_date);

comment on column public.finance_transactions.status is 'pagado = realizado; pendiente = compromiso futuro';
comment on column public.finance_transactions.due_date is 'Fecha de vencimiento para pagos pendientes';
