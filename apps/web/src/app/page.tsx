import Link from "next/link";

import { FOUNDING_MEMBER_MAX_SLOTS, PUBLIC_PLANS, TRIAL_DAYS } from "@ced/types";

import { PublicHeaderLink, PublicHeaderText, PublicSiteHeader } from "@/components/layout/PublicSiteHeader";

const PLAN_STYLES: Record<
  string,
  { border: string; glow: string; badge?: string; badgeClass?: string }
> = {
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
              SYS: ONLINE
            </span>
          </PublicHeaderText>
        }
        center={
          <h1 className="font-[family-name:var(--font-orbitron)] text-base font-bold tracking-widest text-cyan-300 ced-glow-text sm:text-lg">
            CED
          </h1>
        }
        right={<PublicHeaderLink href="/login">LOGIN</PublicHeaderLink>}
      />

      <section className="relative z-10 mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="text-center">
          <div className="mx-auto mb-6 flex h-28 w-28 items-center justify-center rounded-full border-2 border-cyan-400/60 ced-glow sm:h-36 sm:w-36">
            <span className="font-[family-name:var(--font-orbitron)] text-3xl font-bold text-cyan-300 sm:text-4xl">
              CED
            </span>
          </div>
          <h2 className="font-[family-name:var(--font-orbitron)] text-xl font-bold tracking-[0.12em] text-cyan-300 sm:text-2xl md:text-3xl">
            TU ASISTENTE JARVIS CON VOZ EN VIVO
          </h2>
          <p className="mt-3 text-sm text-cyan-100/70">
            Chat + voz + HUD en vivo · Memoria cognitiva · Instagram
          </p>
          <p className="mt-2 text-xs text-cyan-500">
            {TRIAL_DAYS} días gratis al registrarte — sin tarjeta
          </p>
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
                  {plan.highlights.slice(0, 5).map((h) => (
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

        <div className="mt-10 flex flex-wrap justify-center gap-4">
          <Link
            href="/signup"
            className="rounded border-2 border-cyan-400 bg-cyan-400/10 px-8 py-3 font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-wider text-cyan-300 transition hover:bg-cyan-400/25"
          >
            EMPEZAR GRATIS
          </Link>
          <Link
            href="/pricing"
            className="rounded border border-cyan-600 px-8 py-3 text-sm text-cyan-400/90 hover:border-cyan-400"
          >
            VER DETALLE DE PLANES
          </Link>
        </div>

        <p className="mt-8 text-center text-[11px] text-cyan-700">
          Al llegar al límite puedes recargar desde $10 — crédito proporcional, no expira.
        </p>
      </section>
    </main>
  );
}
