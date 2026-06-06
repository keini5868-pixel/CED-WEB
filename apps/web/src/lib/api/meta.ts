import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

async function authHeaders(): Promise<HeadersInit | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) return null;
  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

export type MetaConnectionStatus = {
  connected: boolean;
  username?: string | null;
  followers_count?: number | null;
};

export async function fetchMetaStatus(): Promise<MetaConnectionStatus | null> {
  const headers = await authHeaders();
  if (!headers) return null;
  try {
    const res = await fetch(`${apiUrl()}/v1/meta/status`, { headers });
    if (!res.ok) return null;
    return (await res.json()) as MetaConnectionStatus;
  } catch {
    return null;
  }
}

export async function fetchMetaOAuthUrl(): Promise<string | null> {
  const headers = await authHeaders();
  if (!headers) return null;
  try {
    const res = await fetch(`${apiUrl()}/v1/meta/oauth/url`, { headers });
    if (!res.ok) return null;
    const data = (await res.json()) as { url?: string; detail?: string };
    return data.url ?? null;
  } catch {
    return null;
  }
}
