"use client";

import { useCallback, useState } from "react";
import {
  ChevronRight,
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

type SectionId = "estado" | "navegador" | "sellos" | "politicas" | "equipo";

const SECTIONS: Array<{
  id: SectionId;
  icon: typeof Shield;
  title: string;
  lite: boolean;
  body: string;
}> = [
  {
    id: "estado",
    icon: Shield,
    title: "Estado",
    lite: true,
    body: "Resumen de protección en este navegador y en CED.",
  },
  {
    id: "navegador",
    icon: Globe,
    title: "Navegador",
    lite: true,
    body: "Extensión, DNS cifrado y bloqueo de amenazas.",
  },
  {
    id: "sellos",
    icon: Hash,
    title: "Sellos",
    lite: true,
    body: "Pruebas verificables (hash + tiempo). El documento no se sube.",
  },
  {
    id: "politicas",
    icon: SlidersHorizontal,
    title: "Políticas",
    lite: false,
    body: "Categorías y excepciones para el equipo.",
  },
  {
    id: "equipo",
    icon: Users,
    title: "Equipo",
    lite: false,
    body: "Despliegue y estadísticas agregadas, sin historial individual.",
  },
];

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

function SectionBody({
  id,
  remaining,
  cap,
}: {
  id: SectionId;
  remaining: number;
  cap: number;
}) {
  const [malware, setMalware] = useState(true);
  const [doh, setDoh] = useState(true);
  const [trackers, setTrackers] = useState(true);
  const [cats, setCats] = useState({
    explosivos: false,
    armas: false,
    autolesion: false,
  });

  if (id === "estado") {
    return (
      <div className="space-y-2 text-sm text-cyan-100/80">
        <p>
          Módulo <strong className="text-violet-200">completo</strong> en esta cuenta.
        </p>
        <p>
          Navegador: extensión aún no instalada — las amenazas bloqueadas se verán
          aquí cuando se conecte.
        </p>
        <p>
          Sellos este periodo:{" "}
          <strong className="text-cyan-200">
            {remaining}
            {cap ? ` / ${cap}` : ""}
          </strong>
        </p>
        <p className="text-xs text-cyan-500">
          Shield on-chain sigue con kill-switch de servidor; no se activa solo al
          abrir este panel.
        </p>
      </div>
    );
  }
  if (id === "navegador") {
    return (
      <div className="space-y-3 text-sm text-cyan-100/80">
        <p>
          Chrome/Edge (Manifest V3). La ficha de la Chrome Web Store llega en la
          siguiente fase; aquí ya queda el control.
        </p>
        <label className="flex items-center justify-between gap-3 rounded border border-violet-400/25 px-3 py-2">
          <span>Bloquear malware / phishing conocido</span>
          <input
            type="checkbox"
            checked={malware}
            onChange={(e) => setMalware(e.target.checked)}
          />
        </label>
        <label className="flex items-center justify-between gap-3 rounded border border-violet-400/25 px-3 py-2">
          <span>DNS cifrado (DoH · Cloudflare 1.1.1.1)</span>
          <input type="checkbox" checked={doh} onChange={(e) => setDoh(e.target.checked)} />
        </label>
        <label className="flex items-center justify-between gap-3 rounded border border-violet-400/25 px-3 py-2">
          <span>Quitar rastreadores de URLs</span>
          <input
            type="checkbox"
            checked={trackers}
            onChange={(e) => setTrackers(e.target.checked)}
          />
        </label>
        <p className="text-xs text-cyan-600">
          Los interruptores se guardan en este navegador hasta que la extensión los
          aplique de verdad.
        </p>
      </div>
    );
  }
  if (id === "sellos") {
    return (
      <div className="space-y-3 text-sm text-cyan-100/80">
        <p>
          Cupo:{" "}
          <strong className="text-cyan-200">
            {remaining}
            {cap ? ` / ${cap}` : ""}
          </strong>{" "}
          sellos este periodo.
        </p>
        <p>El PDF o acuerdo no se sube: solo hash + tiempo.</p>
        <Link href="/shield" className="inline-block text-violet-200 underline">
          Abrir demo Shield
        </Link>
      </div>
    );
  }
  if (id === "politicas") {
    return (
      <div className="space-y-3 text-sm text-cyan-100/80">
        <p>Filtro local (no se envían búsquedas a CED). Por defecto apagado en individuos.</p>
        {(
          [
            ["explosivos", "Fabricación de explosivos"],
            ["armas", "Armas"],
            ["autolesion", "Autolesión — mostrar ayuda, no solo bloqueo"],
          ] as const
        ).map(([key, label]) => (
          <label
            key={key}
            className="flex items-center justify-between gap-3 rounded border border-violet-400/25 px-3 py-2"
          >
            <span>{label}</span>
            <input
              type="checkbox"
              checked={cats[key]}
              onChange={(e) => setCats((c) => ({ ...c, [key]: e.target.checked }))}
            />
          </label>
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-2 text-sm text-cyan-100/80">
      <p>Esta cuenta es administrador: acceso completo sin invitación.</p>
      <p>El despliegue a un equipo (Chrome Workspace / políticas) es la fase siguiente.</p>
      <p className="text-xs text-cyan-600">No se registran URLs ni búsquedas de nadie.</p>
    </div>
  );
}

export function SentinelModulePanel({
  forceFull = false,
}: {
  forceFull?: boolean;
}) {
  const access = useSentinelAccess();
  const loaded = forceFull || access.loaded;
  const tier = forceFull ? "full" : access.tier;
  const entitlement = access.entitlement;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<SectionId | null>("estado");

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
  const full = tier === "full";

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
          Pulsa cada tarjeta para abrirla. La rueda del ratón desplaza este panel.
        </p>
      </header>

      {!loaded ? (
        <p className="text-sm text-cyan-500">Cargando acceso…</p>
      ) : tier === "locked" ? (
        <div className="mx-auto max-w-lg rounded-xl border border-violet-400/40 bg-gradient-to-br from-violet-950/50 to-black/60 p-8 text-center">
          <Lock className="mx-auto h-8 w-8 text-violet-200" aria-hidden />
          <h2 className="mt-3 font-[family-name:var(--font-orbitron)] text-xl text-white">
            Módulo cerrado
          </h2>
          <p className="mt-2 text-sm text-cyan-100/75">
            Se abre con Founding o Sentinel Privacy ${SENTINEL_PRIVACY_PRODUCT.priceUsd}/mes.
          </p>
          <UnlockActions busy={busy} onUnlock={() => void unlock()} />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-violet-400/30 bg-violet-950/25 px-4 py-3">
            <span className="inline-flex items-center gap-1.5 font-[family-name:var(--font-orbitron)] text-[10px] tracking-wider text-violet-200">
              <Unlock className="h-3.5 w-3.5" aria-hidden />
              {full ? "MÓDULO COMPLETO" : "LITE · INCLUIDO EN TU PLAN"}
            </span>
            <span className="text-[11px] text-cyan-300/80">
              Sellos {remaining}
              {cap ? ` / ${cap}` : ""} este periodo
            </span>
          </div>
          <div className="space-y-2">
            {SECTIONS.map((section) => {
              const Icon = section.icon;
              const allowed = full || section.lite;
              const expanded = allowed && openId === section.id;
              return (
                <div
                  key={section.id}
                  className={`rounded-lg border ${
                    allowed
                      ? "border-violet-400/35 bg-black/40"
                      : "border-cyan-500/15 bg-black/25"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => {
                      if (!allowed) return;
                      setOpenId((cur) => (cur === section.id ? null : section.id));
                    }}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-violet-500/10"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-violet-300" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-violet-100">
                        {section.title}
                      </span>
                      <span className="block text-[11px] text-cyan-100/65">{section.body}</span>
                    </span>
                    {allowed ? (
                      <ChevronRight
                        className={`h-4 w-4 shrink-0 text-violet-200 transition-transform ${
                          expanded ? "rotate-90" : ""
                        }`}
                        aria-hidden
                      />
                    ) : (
                      <Lock className="h-3.5 w-3.5 shrink-0 text-violet-300/70" aria-label="Cerrado" />
                    )}
                  </button>
                  {expanded ? (
                    <div className="border-t border-violet-400/20 px-4 py-4">
                      <SectionBody id={section.id} remaining={remaining} cap={cap} />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          {tier === "lite" ? (
            <UnlockActions busy={busy} onUnlock={() => void unlock()} />
          ) : null}
        </>
      )}

      {error ? <p className="text-sm text-red-400">{error}</p> : null}
    </div>
  );
}
