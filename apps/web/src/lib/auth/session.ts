import type { User } from "@supabase/supabase-js";

import { isSuperAdmin, resolveUserRole } from "@/lib/auth/roles";
import { isSupabaseConfigured } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

export type SessionInfo = {
  user: User | null;
  role: ReturnType<typeof resolveUserRole>;
  isSuperAdmin: boolean;
};

export async function getSession(): Promise<SessionInfo> {
  if (!isSupabaseConfigured()) {
    return { user: null, role: "client", isSuperAdmin: false };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return { user: null, role: "client", isSuperAdmin: false };
  }

  const metadataRole = user.app_metadata?.role as string | undefined;
  const role = resolveUserRole(user.email, metadataRole);

  return {
    user,
    role,
    isSuperAdmin: isSuperAdmin(user.email, metadataRole),
  };
}
