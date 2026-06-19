/** Variables públicas y comprobaciones de configuración. */

export function isSupabaseConfigured(): boolean {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  return Boolean(url && key && !url.includes("TU_PROYECTO"));
}

export function appUrl(): string {
  return process.env.NEXT_PUBLIC_APP_URL?.trim() || "http://localhost:3000";
}

export function apiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:8000";
}

export function googleMapsKey(): string {
  return process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY?.trim() || "";
}

/** OAuth Google — deshabilitado hasta configurar proveedor en Supabase. */
export function isGoogleAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true";
}
