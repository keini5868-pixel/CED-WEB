-- Perfil automático al registrarse + rol super_admin por email (opcional en Supabase)

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  admin_emails text[];
  assigned_role text := 'client';
begin
  admin_emails := string_to_array(
    coalesce(current_setting('app.super_admin_emails', true), ''),
    ','
  );

  if new.email is not null and lower(new.email) = any (
    select lower(trim(e)) from unnest(admin_emails) as e where trim(e) <> ''
  ) then
    assigned_role := 'super_admin';
  end if;

  insert into public.profiles (id, email, full_name, role)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data->>'full_name', ''),
    assigned_role
  )
  on conflict (id) do update set
    email = excluded.email,
    full_name = coalesce(excluded.full_name, profiles.full_name),
    updated_at = now();

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Alternativa sin app setting: asignar super_admin manualmente en tabla profiles
-- o vía app_metadata.role en Supabase Dashboard → Authentication → Users
