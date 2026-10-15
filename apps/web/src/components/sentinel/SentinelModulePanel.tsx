"use client";

import { useCallback, useState } from "react";
import {
  Globe,
  Hash,
  Lock,
  Shield,
  SlidersHorizontal,
  Unlock,
  Users,
} from "lucide-react";
import Link from "next/link";

import { SENTINEL_PRIVACY_PRODUCT } from "@ced/types";

import { useSentinelAccess, type SentinelTier } from "@/hooks/useSentinelAccess";
import { startSentinelPrivacyCheckout } from "@/lib/api/billing";

const SECTIONS = [
  {
    id: "estado",
    icon: Shield,
    title: "Estado",
    lite: true,
    body: "Resumen de protección en este navegador y en CED. Las cifras de amenazas llegan cuando conectes la extensión.",
  },
  {
    id: "navegador",
    icon: Globe,
    title: "Navegador",
    lite: true,
    body: "Extensión Sentinel Privacy for CED: bloqueo de malware/phishing y DNS cifrado. Instalación y estado — siguiente fase.",
  },
  {
    id: "sellos",
    icon: Hash,
    title: "Sellos",
    lite: true,
    body: "Pruebas verificables (hash + tiempo). El documento no se sube. El cupo viene de tu plan CED o de Sentinel volumen.",
  },
  {
    id: "politicas",
    icon: SlidersHorizontal,
    title: "Políticas",
    lite: false,
    body: "Categorías y excepciones (equipo). Disponible en el módulo completo.",
  },
  {
    id: "equipo",
    icon: Users,
    title: "Equipo",
    lite: false,
    body: "Despliegue a varios usuarios y estadísticas agregadas, sin historial individual.",
  },
] as const;

function UnlockActions({ busy, onUnlock }: { busy: boolean; onUnlock: () => void }) {
  return (
    <div className="mt-6 flex flex-col gap-2 sm:flex-row">
      <button
        type="button"
        disabled={busy}
        onClick={onUnlock}
        className="rounded border border-violet-400/80 bg-violet-500/15 px-4 py-2.5 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-violet-100 hover:bg-violet-500/25 disabled:opacity-50"
      >
        {busy ? "REDIRIGIENDO…" : `DESBLOQUEAR · $${SENTINEL_PRIVACY_PRODUCT.priceUsd}/MES`}
      </button>
      <Link
        href="/dashboard/plans"
        className="rounded border border-amber-400/50 px-4 py-2.5 text-center font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-amber-200 hover:bg-amber-400/10"
      >
        VER FOUNDING (INCLUIDO)
      </Link>
    </div>
  );
}

function LockedHero({
  busy,
  onUnlock,
}: {
  busy: boolean;
  onUnlock: () => void;
}) {
  return (
    <div className="mx-auto max-w-lg rounded-xl border border-violet-400/40 bg-gradient-to-br from-violet-950/50 to-black/60 p-8 text-center shadow-[0_0_40px_rgba(139,92,246,0.18)]">
      <span className="inline-flex h-16 w-16 items-center justify-center rounded-full border border-violet-400/50 bg-violet-500/10">
        <Lock className="h-8 w-8 text-violet-200" aria-hidden />
      </span>
      <p className="mt-4 font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.28em] text-violet-300">
        SENTINEL PRIVACY FOR CED
      </p>
      <h1 className="mt-2 font-[family-name:var(--font-orbitron)] text-xl text-white">
        Módulo cerrado
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-cyan-100/75">
        Centro de seguridad y privacidad del Castillo. Se abre con Founding o con
        Sentinel Privacy. Tu plan CED ya incluye privacidad verificable; aquí se
        organiza el pack completo.
      </p>
      <UnlockActions busy={busy} onUnlock={onUnlock} />
    </div>
  );
}

function SectionGrid({ tier }: { tier: SentinelTier }) {
  const full = tier === "full";
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {SECTIONS.map((section) => {
        const Icon = section.icon;
        const open = full || section.lite;
        return (
          <article
            key={section.id}
            className={`relative rounded-lg border p-4 ${
              open
                ? "border-violet-400/35 bg-black/40"
                : "border-cyan-500/15 bg-black/25 opacity-80"
            }`}
          >
            {!open ? (
              <Lock
                className="absolute right-3 top-3 h-3.5 w-3.5 text-violet-300/70"
                aria-label="Cerrado"
              />
            ) : (
              <Unlock
                className="absolute right-3 top-3 h-3.5 w-3.5 text-emerald-300/80"
                aria-hidden
              />
            )}
            <div className="flex items-center gap-2 pr-6">
              <Icon className="h-4 w-4 text-violet-300" aria-hidden />
              <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-violet-100">
                {section.title}
              </h2>
            </div>
            <p className="mt-2 text-[12px] leading-snug text-cyan-100/70">{section.body}</p>
            <p className="mt-3 text-[10px] uppercase tracking-wider text-cyan-600">
              {open ? (full ? "Listo para conectar" : "Lite · plan CED") : "Requiere módulo completo"}
            </p>
          </article>
        );
      })}
    </div>
  );
}

export function SentinelModulePanel({
  forceFull = false,
}: {
  /** Super admin / panel interno: entra al pack completo sin Stripe. */
  forceFull?: boolean;
}) {
  const access = useSentinelAccess();
  const loaded = forceFull || access.loaded;
  const tier = forceFull ? "full" : access.tier;
  const entitlement = access.entitlement;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const unlock = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const url = await startSentinelPrivacyCheckout(SENTINEL_PRIVACY_PRODUCT.id);
      if (url) window.location.href = url;
      else setError("Stripe no devolvió la página de pago.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo iniciar el pago.");
    } finally {
      setBusy(false);
    }
  }, []);

  const remaining = Number(entitlement.seals_remaining || 0);
  const cap = Number(entitlement.seals_per_month || 0);

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6">
      <header>
        <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.28em] text-violet-400">
          MÓDULO · SENTINEL PRIVACY FOR CED
        </p>
        <h1 className="mt-1 font-[family-name:var(--font-orbitron)] text-lg text-cyan-100 sm:text-xl">
          Seguridad y privacidad
        </h1>
        <p className="mt-1 text-sm text-cyan-100/65">
          Un solo lugar para sellos, navegación protegida y políticas. La extensión
          se engancha aquí; aún no está instalada.
        </p>
      </header>

      {!loaded ? (
        <p className="text-sm text-cyan-500">Cargando acceso…</p>
      ) : tier === "locked" ? (
        <LockedHero busy={busy} onUnlock={() => void unlock()} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-violet-400/30 bg-violet-950/25 px-4 py-3">
            <span className="inline-flex items-center gap-1.5 font-[family-name:var(--font-orbitron)] text-[10px] tracking-wider text-violet-200">
              <Unlock className="h-3.5 w-3.5" aria-hidden />
              {tier === "full" ? "MÓDULO COMPLETO" : "LITE · INCLUIDO EN TU PLAN"}
            </span>
            <span className="text-[11px] text-cyan-300/80">
              Sellos {remaining}
              {cap ? ` / ${cap}` : ""} este periodo
            </span>
            {tier === "lite" ? (
              <span className="text-[11px] text-violet-200/70">
                Completo: Founding o ${SENTINEL_PRIVACY_PRODUCT.priceUsd}/mes
              </span>
            ) : null}
          </div>
          <SectionGrid tier={tier} />
          {tier === "lite" ? (
            <UnlockActions busy={busy} onUnlock={() => void unlock()} />
          ) : null}
        </>
      )}

      {error ? <p className="text-sm text-red-400">{error}</p> : null}
    </div>
  );
}
