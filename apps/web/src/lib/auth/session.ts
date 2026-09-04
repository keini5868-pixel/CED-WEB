import type { User } from "@supabase/supabase-js";

import { isPresenterOwnerEmail, resolveUserRole } from "@/lib/auth/roles";
import { isSupabaseConfigured } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

export type SessionInfo = {
  user: User | null;
  role: ReturnType<typeof resolveUserRole>;
  isSuperAdmin: boolean;
  /** ROBOT presentador: solo emails de SUPER_ADMIN_EMAILS, no el rol de profiles. */
  isPresenterOwner: boolean;
};

export async function getSession(): Promise<SessionInfo> {
  if (!isSupabaseConfigured()) {
    return { user: null, role: "client", isSuperAdmin: false, isPresenterOwner: false };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return { user: null, role: "client", isSuperAdmin: false, isPresenterOwner: false };
  }

  const metadataRole = user.app_metadata?.role as string | undefined;

  const { data: profile } = await supabase
    .from("profiles")
    .select("role")
    .eq("id", user.id)
    .maybeSingle();

  const profileRole = profile?.role as string | undefined;
  const role = resolveUserRole(user.email, metadataRole, profileRole);

  return {
    user,
    role,
    isSuperAdmin: role === "super_admin",
    isPresenterOwner: isPresenterOwnerEmail(user.email),
  };
}
