import type { UserRole } from "@ced/types";

/** Emails con acceso al panel admin (servidor). */
export function getSuperAdminEmails(): string[] {
  const raw =
    process.env.SUPER_ADMIN_EMAILS ||
    process.env.NEXT_PUBLIC_SUPER_ADMIN_EMAILS ||
    "";
  return raw
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

export function resolveUserRole(
  email: string | undefined | null,
  metadataRole?: string | null,
): UserRole {
  const normalized = (email || "").trim().toLowerCase();
  if (metadataRole === "super_admin") {
    return "super_admin";
  }
  if (normalized && getSuperAdminEmails().includes(normalized)) {
    return "super_admin";
  }
  return "client";
}

export function isSuperAdmin(
  email: string | undefined | null,
  metadataRole?: string | null,
): boolean {
  return resolveUserRole(email, metadataRole) === "super_admin";
}
