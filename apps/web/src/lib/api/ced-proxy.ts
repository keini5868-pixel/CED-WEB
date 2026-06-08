/** Rutas BFF same-origin — el servidor Next.js reenvía con la sesión de cookies. */
export function cedApiPath(apiPath: string): string {
  const normalized = apiPath.startsWith("/") ? apiPath.slice(1) : apiPath;
  const withoutV1 = normalized.startsWith("v1/")
    ? normalized.slice(3)
    : normalized;
  return `/api/ced/${withoutV1}`;
}

export function proxyFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(cedApiPath(path), { credentials: "same-origin", ...init });
}
