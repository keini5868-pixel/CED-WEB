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

/** Headers de auth para streams SSE (mismo criterio que proxyFetchAuthed). */
export async function streamAuthHeaders(
  extra?: HeadersInit,
): Promise<HeadersInit> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
    ...(extra as Record<string, string> | undefined),
  };
  try {
    const auth = await authHeaders(false);
    Object.assign(headers, auth as Record<string, string>);
  } catch {
    /* cookies-only fallback */
  }
  return headers;
}
