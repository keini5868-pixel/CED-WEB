import { Suspense } from "react";

import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <main className="ced-auth-shell flex items-center justify-center bg-[var(--ced-bg)]">
      <Suspense
        fallback={
          <p className="font-[family-name:var(--font-orbitron)] text-xs text-cyan-600">
            CARGANDO…
          </p>
        }
      >
        <LoginForm />
      </Suspense>
    </main>
  );
}
