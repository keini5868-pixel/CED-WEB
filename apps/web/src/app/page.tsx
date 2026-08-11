import type { Metadata } from "next";
import Link from "next/link";

import { FOUNDING_MEMBER_MAX_SLOTS, PUBLIC_PLANS, TRIAL_DAYS } from "@ced/types";

import {
  PublicHeaderLink,
  PublicHeaderText,
  PublicSiteHeader,
} from "@/components/layout/PublicSiteHeader";

export const metadata: Metadata = {
  title: "CED — Castillo de la Evolución Digital",
  description:
    "CED es un asistente virtual inteligente que ayuda a gestionar tareas de negocio y personales con voz, texto e imágenes: documentos, mapas y más.",
  openGraph: {
    title: "CED — Castillo de la Evolución Digital",
    description:
      "Asistente virtual con voz en vivo, chat, generación de imágenes y PDF, y herramientas de negocio.",
    url: "https://ced-castillo.com",
    siteName: "CED",
    type: "website",
  },
};

const PLAN_STYLES: Record<
  string,
  { border: string; glow: string; badge?: string; badgeClass?: string }
> = {
  cierre: {
    border: "border-emerald-500/40",
    glow: "hover:border-emerald-400/65 hover:shadow-[0_0_24px_rgba(16,185,129,0.12)]",
    badge: "PM / FITLINE",
    badgeClass: "bg-emerald-500/20 text-emerald-300",
  },
  starter: {
    border: "border-cyan-500/35",
    glow: "hover:border-cyan-400/60",
  },
  pro: {
    border: "border-cyan-400/50",
    glow: "hover:border-cyan-300/70 hover:shadow-[0_0_24px_rgba(0,229,255,0.15)]",
    badge: "POPULAR",
    badgeClass: "bg-cyan-500/20 text-cyan-300",
  },
  elite: {
    border: "border-cyan-500/40",
    glow: "hover:border-cyan-400/65",
  },
  founding: {
    border: "border-amber-400/55",
    glow: "hover:border-amber-300/80 hover:shadow-[0_0_28px_rgba(251,191,36,0.18)]",
    badge: "LIMITED · 50 CUPOS",
    badgeClass: "bg-amber-500/20 text-amber-300",
  },
};

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-x-hidden bg-black">
      <div
        className="pointer-events-none absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at 50% 30%, rgba(0,229,255,0.14) 0%, transparent 55%)",
        }}
      />

      <PublicSiteHeader
        left={
          <PublicHeaderText>
            <span className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.2em] text-cyan-400 sm:text-sm sm:tracking-[0.3em]">
              CED
            </span>
          </PublicHeaderText>
        }
        right={
          <div className="flex items-center gap-2">
            <PublicHeaderLink href="/privacy">Privacidad</PublicHeaderLink>
            <PublicHeaderLink href="/terms">Términos</PublicHeaderLink>
            <PublicHeaderLink href="/login">LOGIN</PublicHeaderLink>
          </div>
        }
      />

      <section className="relative z-10 mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="text-center">
          <h1 className="mx-auto mb-6 flex h-28 w-28 items-center justify-center rounded-full border-2 border-cyan-400/60 ced-glow sm:h-36 sm:w-36">
            <span className="font-[family-name:var(--font-orbitron)] text-3xl font-bold text-cyan-300 sm:text-4xl">
              CED
            </span>
          </h1>
          <p className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.2em] text-cyan-400/90 sm:text-base">
            Castillo de la Evolución Digital
          </p>
          <p className="mx-auto mt-5 max-w-2xl text-sm leading-relaxed text-cyan-100/85 sm:text-base">
            CED es un asistente virtual inteligente que te ayuda a gestionar
            tareas de negocio y personales mediante voz, texto e imágenes.
            Puedes chatear o hablar con CED, generar imágenes y documentos PDF,
            usar mapas y GPS, y publicar en redes cuando tú lo autorices.
          </p>
          <p className="mt-3 text-xs text-cyan-500">
            Página pública — {TRIAL_DAYS} días gratis al registrarte.
          </p>
        </div>
      </section>

      <section
        aria-label="Acciones principales"
        className="relative z-10 mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10"
      >
        <div className="mx-auto flex w-full max-w-md flex-col items-stretch gap-3 sm:max-w-none sm:flex-row sm:items-center sm:justify-center sm:gap-5">
          <Link
            href="/signup"
            className="inline-flex items-center justify-center gap-2 rounded border-2 border-cyan-400 bg-cyan-400/15 px-8 py-3.5 text-center font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-wider text-cyan-200 transition hover:bg-cyan-400/30 hover:text-white sm:min-w-[220px]"
          >
            <span aria-hidden className="text-base leading-none">
              🚀
            </span>
            Empezar gratis
          </Link>
          <a
            href="#planes"
            className="inline-flex items-center justify-center gap-2 rounded border border-cyan-500/55 bg-transparent px-8 py-3.5 text-center text-sm tracking-wide text-cyan-300/90 transition hover:border-cyan-400 hover:bg-cyan-400/5 hover:text-cyan-200 sm:min-w-[220px]"
          >
            <span aria-hidden className="text-base leading-none">
              📋
            </span>
            Ver detalles de planes
          </a>
        </div>
      </section>

      <section
        id="planes"
        className="relative z-10 mx-auto max-w-6xl scroll-mt-24 px-4 pb-16 sm:px-6"
      >
        <h2 className="mb-6 text-center font-[family-name:var(--font-orbitron)] text-sm tracking-[0.2em] text-cyan-400">
          Planes
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
          {PUBLIC_PLANS.filter((p) => p.id !== "free_basic").map((plan) => {
            const style = PLAN_STYLES[plan.id] ?? PLAN_STYLES.starter!;
            const isFounding = plan.id === "founding";
            return (
              <div
                key={plan.id}
                className={`relative flex flex-col rounded-lg border bg-black/50 p-5 transition duration-300 ${style.border} ${style.glow} ${
                  isFounding ? "ring-1 ring-amber-400/30" : ""
                }`}
              >
                {style.badge && (
                  <span
                    className={`absolute -top-2.5 left-4 rounded px-2 py-0.5 font-[family-name:var(--font-orbitron)] text-[9px] font-bold tracking-wider ${style.badgeClass}`}
                  >
                    {style.badge}
                  </span>
                )}
                <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.2em] text-cyan-500">
                  {plan.id === "cierre" && "🎯 PM"}
                  {plan.id === "starter" && "🥉 STARTER"}
                  {plan.id === "pro" && "🥈 PRO"}
                  {plan.id === "elite" && "🥇 ÉLITE"}
                  {plan.id === "founding" && "💎 FOUNDING"}
                </p>
                <h3 className="mt-1 font-[family-name:var(--font-orbitron)] text-lg text-white">
                  {plan.label.replace("CED ", "")}
                </h3>
                <p className="mt-2 font-[family-name:var(--font-orbitron)] text-3xl text-cyan-300">
                  ${plan.priceUsd}
                  <span className="text-sm text-cyan-600">/mes</span>
                </p>
                {isFounding && (
                  <p className="mt-1 text-[10px] text-amber-400/90">
                    Precio bloqueado 6 meses · {FOUNDING_MEMBER_MAX_SLOTS} cupos
                  </p>
                )}
                <ul className="mt-4 flex-1 space-y-1.5 text-xs text-cyan-100/75">
                  {plan.highlights.map((h) => (
                    <li key={h}>· {h}</li>
                  ))}
                </ul>
                <Link
                  href={`/pricing?plan=${plan.id}`}
                  className={`mt-5 block rounded border py-2.5 text-center font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider transition ${
                    isFounding
                      ? "border-amber-400/70 text-amber-200 hover:bg-amber-400/10"
                      : "border-cyan-400/60 text-cyan-300 hover:bg-cyan-400/10"
                  }`}
                >
                  {isFounding ? "RESERVAR CUPO" : "SUSCRIBIRME"}
                </Link>
              </div>
            );
          })}
        </div>

        <p className="mt-8 text-center text-[11px] text-cyan-700">
          Al llegar al límite puedes recargar desde $10 — crédito proporcional, no expira.
        </p>
        <p className="mt-4 text-center text-[11px] text-cyan-600">
          <Link href="/privacy" className="hover:text-cyan-400">
            Política de Privacidad
          </Link>
          {" · "}
          <Link href="/terms" className="hover:text-cyan-400">
            Términos de Servicio
          </Link>
        </p>
        <p className="mt-2 text-center text-[10px] text-cyan-700">
          CED · Castillo de la Evolución Digital · ced-castillo.com
        </p>
      </section>
    </main>
  );
}
