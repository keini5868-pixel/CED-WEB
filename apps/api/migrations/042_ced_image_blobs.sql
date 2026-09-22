-- Bytes de imágenes publicadas / generadas (sobreviven redeploys de Railway)

create table if not exists public.ced_image_blobs (
  file_name text primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  mime text not null default 'image/jpeg',
  image_base64 text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_ced_image_blobs_user_created
  on public.ced_image_blobs (user_id, created_at desc);

alter table public.ced_image_blobs enable row level security;

drop policy if exists ced_image_blobs_service_only on public.ced_image_blobs;
create policy ced_image_blobs_service_only on public.ced_image_blobs
  for all using (false) with check (false);
