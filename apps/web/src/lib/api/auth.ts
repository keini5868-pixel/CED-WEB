import { createClient } from "@/lib/supabase/client";

/** Token Bearer validado con Supabase (sesión local — sin round-trip getUser). */
export async function authHeaders(
  json = true,
): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();
  if (error || !session?.access_token) {
    throw new Error("Sin sesión");
  }
  const headers: Record<string, string> = {
    Authorization: `Bearer ${session.access_token}`,
  };
  if (json) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}
