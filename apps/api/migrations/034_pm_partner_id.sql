-- ID de socio de PM International (Partner Area). No es el Referral ID de CED.

alter table public.profiles
  add column if not exists pm_partner_id text;

comment on column public.profiles.pm_partner_id is
  'ID de socio de PM International. Distinto del referral_code interno de CED.';

comment on column public.pm_structure_partners.partner_ced_id is
  'ID de socio PM International del invitado (no el ID de CED).';
