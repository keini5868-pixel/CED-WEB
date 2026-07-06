import { createClient } from "@/lib/supabase/client";
import { sanitizeAuthNext } from "@/lib/auth/paths";
import { appUrl, PRODUCTION_WEB_URL } from "@/lib/env";

function oauthRedirectBase(): string {
  const base = appUrl();
  if (base.includes("0.0.0.0") || base.includes("localhost:8080")) {
    return PRODUCTION_WEB_URL;
  }
  return base;
}

export async function signInWithGoogle(
  next?: string | null,
): Promise<{ error?: string }> {
  const supabase = createClient();
  const destination = sanitizeAuthNext(next);
  const redirectTo = `${oauthRedirectBase()}/auth/callback?next=${encodeURIComponent(destination)}`;
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo,
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