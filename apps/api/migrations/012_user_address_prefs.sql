-- Preferencias de tratamiento del usuario (Señor/Señora/nombre personalizado)

alter table public.profiles
  add column if not exists preferred_address text,
  add column if not exists gender text check (
    gender is null or gender in ('male', 'female', 'neutral')
  );

comment on column public.profiles.preferred_address is
  'Cómo CED debe dirigirse al usuario: Señor, Señora, Jefe, nombre, etc.';
comment on column public.profiles.gender is
  'male | female | neutral — título por defecto si no hay preferred_address';
