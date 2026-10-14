"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useCallback, useState } from "react";

import { PUBLIC_PLANS } from "@ced/types";

import { PublicHeaderLink, PublicSiteHeader } from "@/components/layout/PublicSiteHeader";
import { startSubscriptionCheckout } from "@/lib/api/billing";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

const BUNDLE_PLANS = PUBLIC_PLANS.filter((p) => p.id === "elite" || p.id === "founding");

function SentinelPrivacyContent() {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const subscribe = useCallback(
    async (planId: string) => {
      setBusy(planId);
      setError(null);
      try {
        if (!isSupabaseConfigured()) {
          setError("Supabase no configurado.");
          return;
        }
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (!user) {
          router.push(`/login?next=${encodeURIComponent(`/pricing?plan=${planId}`)}`);
          return;
        }
        const url = await startSubscriptionCheckout(planId);
        if (url) window.location.href = url;
        else setError("Stripe no devolvió la página de pago.");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al iniciar pago.");
      } finally {
        setBusy(null);
      }
    },
    [router],
  );

  return (
    <main className="ced-page-glow relative min-h-screen overflow-x-hidden text-[var(--ced-text)]">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          background:
            "radial-gradient(ellipse at 50% 15%, rgba(120,80,255,0.18) 0%, transparent 55%)",
        }}
      />

      <PublicSiteHeader
        left={<PublicHeaderLink href="/">← INICIO</PublicHeaderLink>}
        center={
          <h1 className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.25em] text-violet-300 sm:text-xs">
            SENTINEL PRIVACY
          </h1>
        }
        right={<PublicHeaderLink href="/pricing">PLANES CED</PublicHeaderLink>}
      />

      <section className="relative z-10 mx-auto max-w-4xl px-4 py-10 sm:px-6">
        <h2 className="text-center font-[family-name:var(--font-orbitron)] text-2xl text-violet-100">
          Un módulo, dos planes — todo incluido
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-sm text-cyan-100/80">
          Sentinel Privacy no se vende suelto en $12/$29: va{" "}
          <strong className="font-normal text-white">dentro de Élite o Founding</strong> con voz,
          chat, imágenes y sellos verificables (hash + tiempo, contenido fuera de cadena).
        </p>

        <div className="mt-10 grid gap-6 sm:grid-cols-2">
          {BUNDLE_PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`rounded border p-6 ${
                plan.id === "founding"
                  ? "border-amber-400/50 bg-amber-500/5"
                  : "border-violet-400/45 bg-violet-500/10"
              }`}
            >
              <h3 className="font-[family-name:var(--font-orbitron)] text-lg text-white">
                {plan.label}
              </h3>
              <p className="mt-2 font-[family-name:var(--font-orbitron)] text-3xl text-cyan-200">
                ${plan.priceUsd}
                <span className="text-sm text-cyan-600">/mes</span>
              </p>
              <ul className="mt-4 space-y-1 text-sm text-cyan-100/75">
                {plan.highlights.slice(0, 6).map((h) => (
                  <li key={h}>· {h}</li>
                ))}
              </ul>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void subscribe(plan.id)}
                className="mt-6 w-full rounded border border-cyan-400 py-3 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-100 hover:bg-cyan-400/10 disabled:opacity-50"
              >
                {busy === plan.id ? "REDIRIGIENDO A STRIPE…" : "SUSCRIBIRME"}
              </button>
            </div>
          ))}
        </div>

        {error ? <p className="mt-6 text-center text-sm text-red-400">{error}</p> : null}

        <p className="mt-10 text-center text-xs text-cyan-600">
          Demo técnica:{" "}
          <Link href="/shield" className="text-cyan-400 underline">
            /shield
          </Link>{" "}
          (requiere Shield activo en servidor).
        </p>
      </section>
    </main>
  );
}

export default function SentinelPrivacyPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-[var(--ced-bg)] text-violet-300">
          Cargando…
        </main>
      }
    >
      <SentinelPrivacyContent />
    </Suspense>
  );
}
