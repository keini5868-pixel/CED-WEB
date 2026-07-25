-- 023 — Impide escalada de privilegios vía RLS update-own en profiles.
-- Un usuario autenticado no puede cambiar role / founding / price_locked
-- aunque la política profiles_update_own lo permita a nivel de fila.
-- service_role (API) sigue pudiendo actualizar cualquier columna.

create or replace function public.protect_profiles_privileged_columns()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  -- PostgREST / clientes JWT usan authenticated|anon. service_role bypasea.
  if coalesce(auth.role(), '') = 'service_role' then
    return new;
  end if;

  if new.role is distinct from old.role
     or new.is_founding_member is distinct from old.is_founding_member
     or new.founding_slot_number is distinct from old.founding_slot_number
     or new.price_locked_usd is distinct from old.price_locked_usd
     or new.email is distinct from old.email
     or new.id is distinct from old.id
     or new.admin_notes is distinct from old.admin_notes
  then
    raise exception 'No se pueden modificar columnas privilegiadas de profiles';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_protect_profiles_privileged on public.profiles;
create trigger trg_protect_profiles_privileged
  before update on public.profiles
  for each row
  execute function public.protect_profiles_privileged_columns();

comment on function public.protect_profiles_privileged_columns() is
  'Bloquea cambios de role/founding/email desde clientes JWT; solo service_role';
