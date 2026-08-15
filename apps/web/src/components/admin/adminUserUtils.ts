"use client";

function randomChar(pool: string): string {
  const i = Math.floor(Math.random() * pool.length);
  return pool[i] ?? "a";
}

/** Contraseña segura para entregar al usuario (12 chars). */
export function generateSecurePassword(length = 12): string {
  const lower = "abcdefghijkmnopqrstuvwxyz";
  const upper = "ABCDEFGHJKLMNPQRSTUVWXYZ";
  const digits = "23456789";
  const symbols = "!@#$%&*";
  const all = lower + upper + digits + symbols;
  const chars = [
    randomChar(lower),
    randomChar(upper),
    randomChar(digits),
    randomChar(symbols),
  ];
  while (chars.length < length) {
    chars.push(randomChar(all));
  }
  for (let i = chars.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [chars[i], chars[j]] = [chars[j]!, chars[i]!];
  }
  return chars.join("");
}

export const DURATION_OPTIONS: { label: string; value: number | "indefinite" }[] =
  [
    { label: "7 días", value: 7 },
    { label: "14 días", value: 14 },
    { label: "30 días", value: 30 },
    { label: "60 días", value: 60 },
    { label: "90 días", value: 90 },
    { label: "365 días", value: 365 },
    { label: "Indefinido", value: "indefinite" },
  ];

export const ACCESS_TYPE_LABELS: Record<string, string> = {
  paid: "Cliente pago",
  beta: "Beta gratis",
  founding_gift: "Founding regalo",
  coadmin: "Co-admin",
  admin: "Admin",
  trial: "Trial voz",
  free_basic: "Básico gratis",
};

export const STATUS_LABELS: Record<string, string> = {
  active: "Activo",
  trial: "En trial",
  expiring: "Expira pronto",
  expired: "Expirado",
  paused: "Pausado",
  cancelled: "Cancelado",
  past_due: "Pago pendiente",
  sin_plan: "Sin plan",
};
