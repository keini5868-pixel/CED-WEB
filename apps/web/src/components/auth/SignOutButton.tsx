"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { CedButton } from "@ced/ui";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

export function SignOutButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleSignOut() {
    if (!isSupabaseConfigured()) {
      router.push("/");
      return;
    }
    setLoading(true);
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
    setLoading(false);
  }

  return (
    <CedButton variant="ghost" onClick={handleSignOut} disabled={loading}>
      {loading ? "…" : "SALIR"}
    </CedButton>
  );
}
