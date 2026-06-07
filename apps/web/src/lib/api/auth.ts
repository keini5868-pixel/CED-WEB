import { createClient } from "@/lib/supabase/client";

/** Token Bearer validado con Supabase (preferir sobre getSession). */
export async function authHeaders(
  json = true,
): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();
  if (error || !user) {
    throw new Error("Sin sesión");
  }
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
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
