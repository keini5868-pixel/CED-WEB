import { Suspense } from "react";

import { RegisterForm } from "@/components/auth/RegisterForm";

export default function SignupPage() {
  return (
    <main className="ced-auth-shell flex items-center justify-center bg-[var(--ced-bg)]">
      <Suspense
        fallback={
          <p className="font-[family-name:var(--font-orbitron)] text-xs text-cyan-600">
            CARGANDO…
          </p>
        }
      >
        <RegisterForm />
      </Suspense>
    </main>
  );
}
