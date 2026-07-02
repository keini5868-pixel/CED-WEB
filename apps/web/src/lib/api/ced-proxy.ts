import { authHeaders } from "@/lib/api/auth";

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

/** BFF con Bearer del cliente — evita 401 cuando las cookies SSR expiran en voz activa. */
export async function proxyFetchAuthed(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  let headers: HeadersInit = init?.headers ?? {};
  try {
    const auth = await authHeaders(false);
    headers = { ...auth, ...headers };
  } catch {
    /* cookies-only fallback */
  }
  return proxyFetch(path, { ...init, headers });
}
