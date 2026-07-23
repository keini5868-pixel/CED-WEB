import type { Metadata } from "next";
import Link from "next/link";

import { FOUNDING_MEMBER_MAX_SLOTS, PUBLIC_PLANS, TRIAL_DAYS } from "@ced/types";

import { PublicHeaderLink, PublicSiteHeader } from "@/components/layout/PublicSiteHeader";

const APP_NAME = "Castillo de la Evolución Digital";

export const metadata: Metadata = {
  title: `${APP_NAME} — asistente virtual con voz, chat y Google`,
  description:
    "Castillo de la Evolución Digital es un asistente virtual inteligente que ayuda a gestionar tareas de negocio y personales con voz, texto e imágenes. Con tu permiso, puede usar tu cuenta de Google (inicio de sesión, Gmail y Calendar) para actuar solo cuando tú lo solicitas.",
  openGraph: {
    title: APP_NAME,
    description:
      "Asistente virtual con voz y chat. Usa Gmail, Google Calendar y otras herramientas solo con tu autorización explícita.",
    url: "https://ced-castillo.com",
    siteName: APP_NAME,
    type: "website",
  },
};

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
          <span className="inline-flex min-h-[48px] items-center font-[family-name:var(--font-orbitron)] text-[10px] tracking-wide text-cyan-500 sm:text-xs">
            CED
          </span>
        }
        center={
          <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-[0.08em] text-cyan-200 sm:text-sm">
            {APP_NAME}
          </p>
        }
        right={
          <div className="flex items-center gap-2">
            <PublicHeaderLink href="/privacy">Privacidad</PublicHeaderLink>
            <PublicHeaderLink href="/terms">Términos</PublicHeaderLink>
            <PublicHeaderLink href="/login">LOGIN</PublicHeaderLink>
          </div>
        }
      />

      <section className="relative z-10 mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <div className="text-center">
          <p className="text-[11px] uppercase tracking-[0.25em] text-cyan-500">
            Aplicación
          </p>
          <h1 className="mt-3 font-[family-name:var(--font-orbitron)] text-2xl font-bold leading-tight tracking-[0.04em] text-cyan-50 sm:text-3xl md:text-4xl">
            {APP_NAME}
          </h1>
          <p className="mt-2 text-sm text-cyan-400/90">
            Nombre corto de marca: <span className="text-cyan-200">CED</span>
          </p>
        </div>

        <section className="mt-10 rounded-lg border border-cyan-500/25 bg-cyan-500/5 px-5 py-6 text-left">
          <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-semibold tracking-wide text-cyan-200">
            Finalidad de la aplicación
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-cyan-50/90">
            <strong className="text-cyan-100">{APP_NAME}</strong> es un
            asistente virtual inteligente cuya finalidad es ayudarte a gestionar
            tareas de negocio y personales desde un solo lugar. Puedes
            interactuar por <strong>voz</strong> o <strong>texto</strong>, pedir
            análisis, generar imágenes y documentos PDF, usar mapas y
            navegación, y —solo cuando tú lo indiques— publicar contenido en
            redes sociales conectadas.
          </p>
          <p className="mt-3 text-sm leading-relaxed text-cyan-50/90">
            Esta página es pública: no necesitas iniciar sesión para conocer la
            finalidad de la aplicación. El registro y el login existen para
            usar las funciones con tu cuenta.
          </p>
        </section>

        <section className="mt-6 rounded-lg border border-white/15 bg-black/40 px-5 py-6 text-left">
          <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-semibold tracking-wide text-cyan-200">
            Por qué solicitamos acceso a Google
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-cyan-50/90">
            {APP_NAME} puede pedir permiso para usar tu cuenta de Google con
            estos fines concretos (siempre con tu consentimiento en la pantalla
            de Google):
          </p>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-cyan-50/90">
            <li>
              <strong className="text-cyan-100">Inicio de sesión (OAuth):</strong>{" "}
              crear o acceder a tu cuenta de forma segura sin que guardemos tu
              contraseña de Google.
            </li>
            <li>
              <strong className="text-cyan-100">Gmail:</strong> leer o enviar
              correos únicamente cuando tú se lo pides al asistente.
            </li>
            <li>
              <strong className="text-cyan-100">Google Calendar:</strong> consultar
              o crear eventos únicamente cuando tú se lo pides.
            </li>
          </ul>
          <p className="mt-3 text-sm leading-relaxed text-cyan-50/90">
            No usamos tus datos de Google para publicidad. Puedes revocar el
            acceso en cualquier momento desde la configuración de tu cuenta de
            Google. Detalles en nuestra{" "}
            <Link href="/privacy" className="text-cyan-300 underline hover:text-cyan-100">
              Política de Privacidad
            </Link>
            .
          </p>
        </section>

        <section className="mt-6 rounded-lg border border-white/10 bg-black/30 px-5 py-6 text-left">
          <h2 className="font-[family-name:var(--font-orbitron)] text-sm font-semibold tracking-wide text-cyan-200">
            Funciones principales
          </h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-cyan-50/90">
            <li>Chat y voz en vivo con el asistente.</li>
            <li>Integración opcional con Gmail y Google Calendar.</li>
            <li>Generación de imágenes y documentos PDF.</li>
            <li>Mapas / GPS (Modo Conducir) cuando lo actives.</li>
            <li>
              Publicación en Facebook o Instagram solo si conectas esas cuentas
              y lo autorizas.
            </li>
          </ul>
          <p className="mt-4 text-xs text-cyan-500">
            {TRIAL_DAYS} días gratis al registrarte — sin tarjeta.
          </p>
        </section>
      </section>

      <section className="relative z-10 mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <h2 className="mb-6 text-center font-[family-name:var(--font-orbitron)] text-sm tracking-[0.2em] text-cyan-400">
          Planes
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
          {APP_NAME} · ced-castillo.com
        </p>
      </section>
    </main>
  );
}
