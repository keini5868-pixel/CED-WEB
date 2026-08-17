"use client";

import { ChangePasswordForm } from "@/components/account/ChangePasswordForm";
import { ThemeAppearanceToggle } from "@/components/account/ThemeAppearanceToggle";
import { ReferralIdCard } from "@/components/referrals/ReferralIdCard";

export function AccountPanel() {
  return (
    <div className="mx-auto max-w-lg space-y-6 px-4 py-6">
      <div>
        <h1 className="font-[family-name:var(--font-orbitron)] text-lg tracking-wide text-[var(--ced-text-primary)] sm:text-xl">
          Cuenta
        </h1>
        <p className="mt-1 text-sm text-[var(--ced-text-muted)]">
          Ajustes de acceso. El cambio de contraseña no envía correo ni depende
          de recuperación por email.
        </p>
      </div>

      <ThemeAppearanceToggle />

      <ReferralIdCard />

      <section className="rounded border border-cyan-500/25 bg-black/40 p-4">
        <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
          CAMBIAR CONTRASEÑA
        </h2>
        <p className="mt-1 mb-4 text-xs text-cyan-100/60">
          Escribe tu contraseña actual y la nueva (mínimo 8 caracteres).
        </p>
        <ChangePasswordForm />
      </section>
    </div>
  );
}
