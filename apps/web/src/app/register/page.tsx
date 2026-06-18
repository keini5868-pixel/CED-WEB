import { Suspense } from "react";

import { RegisterForm } from "@/components/auth/RegisterForm";

export default function RegisterPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--ced-bg)] px-4">
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
