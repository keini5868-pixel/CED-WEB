"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { SENTINEL_PRIVACY_PRODUCT } from "@ced/types";

import { PublicHeaderLink, PublicSiteHeader } from "@/components/layout/PublicSiteHeader";
import { confirmCheckoutSession, startSentinelPrivacyCheckout } from "@/lib/api/billing";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/env";

function SentinelPrivacyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const billing = searchParams.get("billing");
  const sessionId = searchParams.get("session_id");
  const pendingPlan = searchParams.get("plan");
  const product = SENTINEL_PRIVACY_PRODUCT;

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
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

  useEffect(() => {
    if (billing !== "sentinel_success" || !sessionId) return;
    void confirmCheckoutSession(sessionId)
      .then(() => {
        setSuccessMsg(
          `Suscripción ${product.label} activa. Tus sellos aparecerán cuando uses CED Shield.`,
        );
      })
      .catch((e: Error) => setError(e.message));
  }, [billing, sessionId, product.label]);

  const subscribe = useCallback(async () => {
    setBusy(true);
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
        router.push(`/login?next=${encodeURIComponent("/sentinel-privacy")}`);
        return;
      }
      const url = await startSentinelPrivacyCheckout(product.id);
      if (url) window.location.href = url;
      else setError("Stripe no devolvió la página de pago.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al iniciar pago.");
    } finally {
      setBusy(false);
    }
  }, [router, product.id]);

  useEffect(() => {
    if (pendingPlan !== product.id || loggedIn !== true || busy) return;
    void subscribe();
  }, [pendingPlan, loggedIn, busy, subscribe, product.id]);

  return (
    <main className="ced-page-glow relative min-h-screen overflow-x-hidden text-[var(--ced-text)]">
      <PublicSiteHeader
        left={<PublicHeaderLink href="/">← CED</PublicHeaderLink>}
        center={
          <span className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.25em] text-violet-300">
            SENTINEL PRIVACY
          </span>
        }
        right={<PublicHeaderLink href="/pricing">PLANES CED</PublicHeaderLink>}
      />

      <section className="relative z-10 mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <p className="text-center text-[10px] uppercase tracking-[0.2em] text-amber-300/90">
          Línea aparte · otra suscripción Stripe
        </p>
        <h1 className="mt-2 text-center font-[family-name:var(--font-orbitron)] text-2xl text-white">
          {product.label}
        </h1>
        <p className="mt-2 text-center text-sm text-violet-200/90">{product.tagline}</p>

        <div className="mt-8 rounded border border-violet-500/40 bg-black/40 p-6">
          <p className="font-[family-name:var(--font-orbitron)] text-4xl text-violet-100">
            ${product.priceUsd}
            <span className="text-base text-violet-500">/mes</span>
          </p>
          <p className="mt-2 text-sm text-violet-200/85">{product.homeSubtitle}</p>

          <h2 className="mt-6 font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-cyan-400">
            QUÉ ES
          </h2>
          <ul className="mt-2 space-y-2 text-sm text-cyan-100/85">
            {product.highlights.map((h) => (
              <li key={h}>· {h}</li>
            ))}
          </ul>

          <h2 className="mt-6 font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-amber-400">
            QUÉ NO ES (NO MEZCLAR CON CED)
          </h2>
          <ul className="mt-2 space-y-2 text-sm text-amber-100/85">
            {product.notIncluded.map((h) => (
              <li key={h}>· {h}</li>
            ))}
          </ul>

          <button
            type="button"
            disabled={busy}
            onClick={() => void subscribe()}
            className="mt-8 w-full rounded border border-violet-400 py-3 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-violet-100 hover:bg-violet-500/15 disabled:opacity-50"
          >
            {busy ? "REDIRIGIENDO A STRIPE…" : `SUSCRIBIR ${product.label.toUpperCase()}`}
          </button>
        </div>

        {successMsg ? (
          <p className="mt-4 text-center text-sm text-emerald-300">{successMsg}</p>
        ) : null}
        {error ? <p className="mt-4 text-center text-sm text-red-400">{error}</p> : null}

        <p className="mt-8 text-center text-xs text-cyan-600">
          Demo:{" "}
          <Link href="/shield" className="text-cyan-400 underline">
            /shield
          </Link>
        </p>
      </section>
    </main>
  );
}

export default function SentinelPrivacyPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center text-violet-300">
          Cargando…
        </main>
      }
    >
      <SentinelPrivacyContent />
    </Suspense>
  );
}
