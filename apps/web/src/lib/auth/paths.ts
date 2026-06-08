/** Rutas canónicas de auth y app (Fase 1). */

export const DASHBOARD_PATH = "/dashboard";
export const DRIVE_PATH = "/drive";
export const ADMIN_PATH = "/admin";
export const LOGIN_PATH = "/login";
export const SIGNUP_PATH = "/signup";
export const FORGOT_PASSWORD_PATH = "/forgot-password";
export const RESET_PASSWORD_PATH = "/reset-password";
export const VERIFY_EMAIL_PATH = "/verify-email";

export const PUBLIC_AUTH_PREFIXES = [
  LOGIN_PATH,
  SIGNUP_PATH,
  "/register",
  FORGOT_PASSWORD_PATH,
  RESET_PASSWORD_PATH,
  VERIFY_EMAIL_PATH,
  "/auth",
] as const;

export const PROTECTED_PREFIXES = [DASHBOARD_PATH, DRIVE_PATH, ADMIN_PATH, "/app"] as const;
