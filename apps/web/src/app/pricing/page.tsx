"use client";

import Link from "next/link";
import { useState } from "react";

import { FOUNDING_MEMBER_MAX_SLOTS, PUBLIC_PLANS } from "@ced/types";

import { startSubscriptionCheckout } from "@/lib/api/billing";

export default function PricingPage() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const subscribe = async (planId: string) => {
    setBusy(planId);
    setError(null);
    try {
      const url = await startSubscriptionCheckout(planId);
      if (url) window.location.href = url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al iniciar pago.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-black text-cyan-100">
      <div
        className="pointer-events-none absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at 50% 20%, rgba(0,229,255,0.12) 0%, transparent 55%)",
        }}
      />

      <header className="relative z-10 flex items-center justify-between border-b border-cyan-500/20 px-6 py-4">
        <Link href="/" className="text-xs tracking-widest text-cyan-500 hover:text-cyan-300">
          ← INICIO
        </Link>
        <h1 className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.25em] text-cyan-300">
          PLANES CED
        </h1>
        <Link href="/login" className="text-xs text-cyan-500 hover:text-cyan-300">
          LOGIN
        </Link>
      </header>

      <section className="relative z-10 mx-auto max-w-5xl px-6 py-12">
        <p className="text-center text-xs text-cyan-500">
          7 días gratis al registrarte · sin tarjeta
        </p>
        <h2 className="mt-2 text-center font-[family-name:var(--font-orbitron)] text-2xl text-cyan-300">
          Elige tu plan
        </h2>

        <div className="mt-10 grid gap-6 md:grid-cols-2">
          {PUBLIC_PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`rounded border p-6 ${
                plan.id === "founding"
                  ? "border-amber-400/50 bg-amber-400/5"
                  : "border-cyan-500/30 bg-black/40"
              }`}
            >
              <h3 className="font-[family-name:var(--font-orbitron)] text-lg text-white">
                {plan.label}
              </h3>
              <p className="mt-2 font-[family-name:var(--font-orbitron)] text-3xl text-cyan-300">
                ${plan.priceUsd}
                <span className="text-sm text-cyan-600">/mes</span>
              </p>
              {plan.id === "founding" && (
                <p className="mt-1 text-xs text-amber-400">
                  Cupos {FOUNDING_MEMBER_MAX_SLOTS} · precio bloqueado de por vida
                </p>
              )}
              <ul className="mt-4 space-y-1 text-sm text-cyan-100/75">
                {plan.highlights.map((h) => (
                  <li key={h}>· {h}</li>
                ))}
              </ul>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void subscribe(plan.id)}
                className="mt-6 w-full rounded border border-cyan-400 py-3 font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-cyan-300 hover:bg-cyan-400/10 disabled:opacity-50"
              >
                {busy === plan.id ? "REDIRIGIENDO…" : "SUSCRIBIRME"}
              </button>
            </div>
          ))}
        </div>

        {error && (
          <p className="mt-6 text-center text-sm text-red-400">{error}</p>
        )}

        <p className="mt-10 text-center text-xs text-cyan-600">
          Las recargas de voz extra solo aparecen cuando agotas tu cupo diario — no expiran.
        </p>
      </section>
    </main>
  );
}
