-- Recordatorios HUD — sincronizados desde popups y consultables por chat/voz

create table if not exists public.hud_reminders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  text text not null,
  reminder_date date not null,
  reminder_time time not null default '09:00',
  created_at timestamptz not null default now()
);

create index if not exists hud_reminders_user_date_idx
  on public.hud_reminders (user_id, reminder_date, reminder_time);

alter table public.hud_reminders enable row level security;

create policy hud_reminders_service_only on public.hud_reminders
  for all using (false) with check (false);

comment on table public.hud_reminders is 'Recordatorios CED HUD — solo service_role';
