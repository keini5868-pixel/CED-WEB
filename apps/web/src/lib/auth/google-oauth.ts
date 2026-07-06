import { createClient } from "@/lib/supabase/client";
import { sanitizeAuthNext } from "@/lib/auth/paths";
import { appUrl } from "@/lib/env";

export async function signInWithGoogle(
  next?: string | null,
): Promise<{ error?: string }> {
  const supabase = createClient();
  const destination = sanitizeAuthNext(next);
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${appUrl()}/auth/callback?next=${encodeURIComponent(destination)}`,
      queryParams: {
        access_type: "offline",
        prompt: "consent",
      },
    },
  });
  if (error) {
    return { error: error.message };
  }
  return {};
}
