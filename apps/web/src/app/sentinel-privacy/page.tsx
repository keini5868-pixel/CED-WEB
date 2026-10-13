"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { SENTINEL_PUBLIC_PLANS } from "@ced/types";

import { PublicHeaderLink, PublicSiteHeader } from "@/components/layout/PublicSiteHeader";
import { confirmCheckoutSession, startSentinelPrivacyCheckout } from "@/lib/api/billing";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

function SentinelPrivacyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pendingPlan = searchParams.get("plan");
  const billing = searchParams.get("billing");
  const sessionId = searchParams.get("session_id");
  const checkoutNext = pendingPlan
    ? `/sentinel-privacy?plan=${encodeURIComponent(pendingPlan)}`
    : "/sentinel-privacy";
  const loginHref = `/login?next=${encodeURIComponent(checkoutNext)}`;
  const signupHref = `/signup?next=${encodeURIComponent(checkoutNext)}`;

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      setLoggedIn(false);
      return;
    }
    void createClient()
      .auth.getUser()
      .then(({ data }) => setLoggedIn(Boolean(data.user)));
  }, []);

  useEffect(() => {
    if (billing !== "sentinel_success" || !sessionId || loggedIn !== true) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await confirmCheckoutSession(sessionId);
        if (cancelled) return;
        if (result.ok) {
          const plan = SENTINEL_PUBLIC_PLANS.find((p) => p.id === result.plan_id);
          setSuccessMsg(
            plan
              ? `Suscripción activa: ${plan.label}. Cuando CED Shield esté habilitado en tu entorno, podrás usar tus ${plan.sealsPerMonth} sellos/mes.`
              : "Suscripción Sentinel Privacy activa.",
          );
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "No se pudo confirmar el pago.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [billing, sessionId, loggedIn]);

  const subscribe = useCallback(
    async (planId: string) => {
      setBusy(planId);
      setError(null);
      setSuccessMsg(null);
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
          router.push(`/login?next=${encodeURIComponent(`/sentinel-privacy?plan=${planId}`)}`);
          return;
        }
        const url = await startSentinelPrivacyCheckout(planId);
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

  useEffect(() => {
    if (!pendingPlan || loggedIn !== true || busy) return;
    const valid = SENTINEL_PUBLIC_PLANS.some((p) => p.id === pendingPlan);
    if (!valid) return;
    void subscribe(pendingPlan);
  }, [pendingPlan, loggedIn, busy, subscribe]);

  return (
    <main className="ced-page-glow relative min-h-screen overflow-x-hidden text-[var(--ced-text)]">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          background:
            "radial-gradient(ellipse at 50% 15%, rgba(120,80,255,0.18) 0%, transparent 55%), radial-gradient(ellipse at 80% 70%, rgba(0,229,255,0.08) 0%, transparent 45%)",
        }}
      />

      <PublicSiteHeader
        left={<PublicHeaderLink href="/">← CED</PublicHeaderLink>}
        center={
          <h1 className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.25em] text-violet-300 sm:text-xs">
            SENTINEL PRIVACY
          </h1>
        }
        right={
          loggedIn ? (
            <PublicHeaderLink href="/shield">SHIELD DEMO</PublicHeaderLink>
          ) : (
            <PublicHeaderLink href={loginHref}>LOGIN</PublicHeaderLink>
          )
        }
      />

      <section className="relative z-10 mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-12">
        <p className="text-center text-xs uppercase tracking-widest text-violet-400/90">
          Producto aparte · privacidad selectiva · Midnight / ZK
        </p>
        <h2 className="mt-3 text-center font-[family-name:var(--font-orbitron)] text-2xl text-violet-200 sm:text-3xl">
          Sellos verificables sin exponer el contenido
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-sm leading-relaxed text-cyan-100/75">
          <strong className="font-normal text-violet-200">Sentinel Privacy</strong> no es tu plan
          de voz Jarvis ni el chat CED: es la capa de confianza para PDFs, acuerdos y
          entregables. En cadena solo va el hash y la marca de tiempo; el documento sensible
          permanece fuera.
        </p>

        {billing === "sentinel_cancelled" && (
          <p className="mt-6 rounded border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-center text-sm text-amber-200">
            Pago cancelado. Elige un plan cuando quieras.
          </p>
        )}
        {successMsg && (
          <p className="mt-6 rounded border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-center text-sm text-emerald-100">
            {successMsg}
          </p>
        )}

        {!loggedIn && loggedIn !== null && (
          <p className="mt-6 text-center text-xs text-cyan-400">
            <Link href={loginHref} className="underline hover:text-cyan-200">
              Inicia sesión
            </Link>{" "}
            con tu cuenta CED o{" "}
            <Link href={signupHref} className="underline hover:text-cyan-200">
              regístrate
            </Link>{" "}
            para suscribirte.
          </p>
        )}

        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {SENTINEL_PUBLIC_PLANS.map((plan, idx) => (
            <div
              key={plan.id}
              className={`rounded border p-6 ${
                idx === 1
                  ? "border-violet-400/50 bg-violet-500/10"
                  : "border-violet-500/25 bg-black/40"
              }`}
            >
              <h3 className="font-[family-name:var(--font-orbitron)] text-base text-white">
                {plan.label}
              </h3>
              <p className="mt-2 font-[family-name:var(--font-orbitron)] text-3xl text-violet-200">
                ${plan.priceUsd}
                <span className="text-sm text-violet-500">/mes</span>
              </p>
              <p className="mt-1 text-xs text-violet-300/80">
                {plan.sealsPerMonth} sellos verificables / mes
              </p>
              <ul className="mt-4 space-y-1 text-sm text-cyan-100/75">
                {plan.highlights.map((h) => (
                  <li key={h}>· {h}</li>
                ))}
              </ul>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void subscribe(plan.id)}
                className="mt-6 w-full rounded border border-violet-400/80 py-3 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-violet-100 hover:bg-violet-500/15 disabled:opacity-50"
              >
                {busy === plan.id ? "REDIRIGIENDO A STRIPE…" : "SUSCRIBIR SENTINEL"}
              </button>
            </div>
          ))}
        </div>

        {error && <p className="mt-6 text-center text-sm text-red-400">{error}</p>}

        <div className="mt-12 rounded border border-cyan-900/40 bg-black/30 p-5 text-xs leading-relaxed text-cyan-600">
          <p>
            La demo técnica vive en{" "}
            <Link href="/shield" className="text-cyan-400 hover:text-cyan-200">
              /shield
            </Link>{" "}
            y requiere{" "}
            <code className="text-cyan-500">CED_SHIELD_ENABLED=true</code> en el servidor. En
            producción el módulo sigue apagado por defecto; tu suscripción queda registrada y
            lista para cuando actives Shield en tu despliegue.
          </p>
          <p className="mt-2">
            ¿Productividad con IA?{" "}
            <Link href="/pricing" className="text-cyan-400 hover:text-cyan-200">
              Planes CED
            </Link>
            .
          </p>
        </div>
      </section>
    </main>
  );
}

export default function SentinelPrivacyPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-[var(--ced-bg)] text-violet-300">
          Cargando Sentinel Privacy…
        </main>
      }
    >
      <SentinelPrivacyContent />
    </Suspense>
  );
}
