import { Suspense } from "react";

import { VerifyEmailPanel } from "@/components/auth/VerifyEmailPanel";

export default function VerifyEmailPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--ced-bg)] px-4">
      <Suspense
        fallback={
          <p className="font-[family-name:var(--font-orbitron)] text-xs text-cyan-600">
            CARGANDO…
          </p>
        }
      >
        <VerifyEmailPanel />
      </Suspense>
    </main>
  );
}
