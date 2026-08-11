"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { FOUNDING_MEMBER_MAX_SLOTS, PUBLIC_PLANS } from "@ced/types";

import { startSubscriptionCheckout } from "@/lib/api/billing";
import { PublicHeaderLink, PublicSiteHeader } from "@/components/layout/PublicSiteHeader";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

function PricingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pendingPlan = searchParams.get("plan");
  const cancelled = searchParams.get("billing") === "cancelled";
  const checkoutNext = pendingPlan
    ? `/pricing?plan=${encodeURIComponent(pendingPlan)}`
    : "/pricing";
  const signupHref = `/signup?next=${encodeURIComponent(checkoutNext)}`;
  const loginHref = `/login?next=${encodeURIComponent(checkoutNext)}`;

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      setLoggedIn(false);
      return;
    }
    void createClient()
      .auth.getUser()
      .then(({ data }) => setLoggedIn(Boolean(data.user)));
  }, []);

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
        else setError("Stripe no devolvió la página de pago. Revisa la configuración.");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al iniciar pago.");
      } finally {
        setBusy(null);
      }
    },
    [router],
  );

  useEffect(() => {
    if (!pendingPlan || loggedIn !== true || busy) return;
    const valid = PUBLIC_PLANS.some((p) => p.id === pendingPlan && p.id !== "free_basic");
    if (!valid) return;
    void subscribe(pendingPlan);
  }, [pendingPlan, loggedIn, busy, subscribe]);

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-black text-cyan-100">
      <div
        className="pointer-events-none absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at 50% 20%, rgba(0,229,255,0.12) 0%, transparent 55%)",
        }}
      />

      <PublicSiteHeader
        left={<PublicHeaderLink href="/">← INICIO</PublicHeaderLink>}
        center={
          <h1 className="font-[family-name:var(--font-orbitron)] text-xs tracking-[0.2em] text-cyan-300 sm:text-sm sm:tracking-[0.25em]">
            PLANES CED
          </h1>
        }
        right={
          loggedIn ? (
            <PublicHeaderLink href="/dashboard">DASHBOARD</PublicHeaderLink>
          ) : (
            <PublicHeaderLink href={loginHref}>LOGIN</PublicHeaderLink>
          )
        }
      />

      <section className="relative z-10 mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-12">
        <p className="text-center text-xs text-cyan-500">
          7 días gratis al registrarte · sin tarjeta
        </p>
        <h2 className="mt-2 text-center font-[family-name:var(--font-orbitron)] text-2xl text-cyan-300">
          Elige tu plan
        </h2>

        {cancelled && (
          <p className="mt-4 rounded border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-center text-sm text-amber-200">
            Pago cancelado. Puedes elegir otro plan cuando quieras.
          </p>
        )}

        {!loggedIn && loggedIn !== null && (
          <p className="mt-4 text-center text-xs text-cyan-400">
            Debes{" "}
            <Link href={loginHref} className="underline hover:text-cyan-200">
              iniciar sesión
            </Link>{" "}
            para pagar. Si no tienes cuenta,{" "}
            <Link href={signupHref} className="underline hover:text-cyan-200">
              créala aquí
            </Link>
            .
          </p>
        )}

        <div className="mt-10 grid gap-6 md:grid-cols-2">
          {PUBLIC_PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`rounded border p-6 ${
                plan.id === "founding"
                  ? "border-amber-400/50 bg-amber-400/5"
                  : plan.id === "cierre"
                    ? "border-emerald-500/40 bg-emerald-500/5"
                    : plan.id === "free_basic"
                      ? "border-cyan-500/20 bg-black/30"
                      : "border-cyan-500/30 bg-black/40"
              }`}
            >
              <h3 className="font-[family-name:var(--font-orbitron)] text-lg text-white">
                {plan.label}
              </h3>
              <p className="mt-2 font-[family-name:var(--font-orbitron)] text-3xl text-cyan-300">
                {plan.priceUsd === 0 ? (
                  "Gratis"
                ) : (
                  <>
                    ${plan.priceUsd}
                    <span className="text-sm text-cyan-600">/mes</span>
                  </>
                )}
              </p>
              {plan.id === "founding" && (
                <p className="mt-1 text-xs text-amber-400">
                  Cupos {FOUNDING_MEMBER_MAX_SLOTS} · precio bloqueado por 6 meses
                </p>
              )}
              {plan.id === "cierre" && (
                <p className="mt-1 text-xs text-emerald-400/90">
                  Prueba FitLine: 20 min de voz · 24 horas · luego $20/mes
                </p>
              )}
              {plan.id === "free_basic" && (
                <p className="mt-1 text-xs text-cyan-500">Acceso por tiempo limitado</p>
              )}
              <ul className="mt-4 space-y-1 text-sm text-cyan-100/75">
                {plan.highlights.map((h) => (
                  <li key={h}>· {h}</li>
                ))}
              </ul>
              {plan.id === "free_basic" ? (
                <Link
                  href={signupHref}
                  className="mt-6 block w-full rounded border border-cyan-700 py-3 text-center font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-cyan-400 hover:bg-cyan-400/5"
                >
                  EMPEZAR GRATIS
                </Link>
              ) : plan.id === "cierre" ? (
                <div className="mt-6 space-y-2">
                  <Link
                    href="/signup?offer=cierre"
                    className="block w-full rounded border border-emerald-400/70 py-3 text-center font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-emerald-200 hover:bg-emerald-400/10"
                  >
                    PROBAR 24 H GRATIS
                  </Link>
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void subscribe(plan.id)}
                    className="w-full rounded border border-cyan-500/40 py-2.5 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-cyan-400 hover:bg-cyan-400/5 disabled:opacity-50"
                  >
                    {busy === plan.id ? "REDIRIGIENDO…" : "O SUSCRIBIRME YA · $20/MES"}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void subscribe(plan.id)}
                  className="mt-6 w-full rounded border border-cyan-400 py-3 font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-wider text-cyan-300 hover:bg-cyan-400/10 disabled:opacity-50"
                >
                  {busy === plan.id ? "REDIRIGIENDO A STRIPE…" : "SUSCRIBIRME"}
                </button>
              )}
            </div>
          ))}
        </div>

        {error && <p className="mt-6 text-center text-sm text-red-400">{error}</p>}

        <p className="mt-10 text-center text-xs text-cyan-600">
          Al alcanzar cualquier límite (voz, imágenes, PDF, búsquedas…) puedes recargar
          desde $10 — crédito proporcional al monto, no expira. Aplica a todos los planes.
        </p>
      </section>
    </main>
  );
}

export default function PricingPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-black text-cyan-500">
          Cargando planes…
        </main>
      }
    >
      <PricingContent />
    </Suspense>
  );
}
