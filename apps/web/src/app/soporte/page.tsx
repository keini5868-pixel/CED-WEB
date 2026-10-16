"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import SupportChatPanel from "@/components/support/SupportChatPanel";
import { isSupabaseConfigured } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

export default function SoportePage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const login = `/login?next=${encodeURIComponent("/soporte")}`;
    if (!isSupabaseConfigured()) {
      router.replace(login);
      return;
    }
    void createClient()
      .auth.getUser()
      .then(({ data }) => {
        if (!data.user) {
          router.replace(login);
          return;
        }
        setReady(true);
      })
      .catch(() => router.replace(login));
  }, [router]);

  if (!ready) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#0a0f18] text-sm text-cyan-200">
        Abriendo soporte…
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#0a0f18]">
      <SupportChatPanel
        layout="page"
        onClose={() => router.push("/")}
        onMessageRead={() => {}}
      />
    </main>
  );
}
