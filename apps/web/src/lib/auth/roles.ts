import type { UserRole } from "@ced/types";

function normalizeAdminEmail(value: string): string {
  return value.trim().replace(/^["']+|["']+$/g, "").toLowerCase();
}

/** Emails con acceso al panel admin — solo servidor (nunca NEXT_PUBLIC_). */
export function getSuperAdminEmails(): string[] {
  // En el navegador no leemos allowlist: evita filtrarla al bundle/cliente.
  if (typeof window !== "undefined") {
    return [];
  }
  const raw = process.env.SUPER_ADMIN_EMAILS || "";
  return raw
    .split(",")
    .map(normalizeAdminEmail)
    .filter(Boolean);
}

export function resolveUserRole(
  email: string | undefined | null,
  metadataRole?: string | null,
  profileRole?: string | null,
): UserRole {
  const normalized = normalizeAdminEmail(email || "");
  if (metadataRole === "super_admin" || profileRole === "super_admin") {
    return "super_admin";
  }
  if (normalized && getSuperAdminEmails().includes(normalized)) {
    return "super_admin";
  }
  return "client";
}

export function isPresenterOwnerEmail(
  email: string | undefined | null,
  allowlist?: readonly string[],
): boolean {
  const emails = [...(allowlist ?? (typeof window === "undefined" ? getSuperAdminEmails() : []))]
    .map(normalizeAdminEmail)
    .filter(Boolean);
  const normalized = normalizeAdminEmail(email || "");
  return Boolean(normalized && emails.includes(normalized));
}

export function isSuperAdmin(
  email: string | undefined | null,
  metadataRole?: string | null,
  profileRole?: string | null,
): boolean {
  return resolveUserRole(email, metadataRole, profileRole) === "super_admin";
}
