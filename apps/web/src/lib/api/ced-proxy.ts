/** Rutas BFF same-origin — el servidor Next.js reenvía con la sesión de cookies. */
export function cedApiPath(apiPath: string): string {
  const normalized = apiPath.startsWith("/") ? apiPath.slice(1) : apiPath;
  return `/api/ced/${normalized}`;
}
