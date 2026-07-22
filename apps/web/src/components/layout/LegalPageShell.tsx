import Link from "next/link";
import type { ReactNode } from "react";

import { PublicHeaderLink, PublicSiteHeader } from "@/components/layout/PublicSiteHeader";

/** Layout público para documentos legales (privacidad / términos). */
export function LegalPageShell({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
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
        left={
          <PublicHeaderLink href="/">
            <span className="font-[family-name:var(--font-orbitron)] tracking-wider">
              CED
            </span>
          </PublicHeaderLink>
        }
        center={
          <span className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-[0.2em] text-cyan-400/80">
            CASTILLO DE LA EVOLUCIÓN DIGITAL
          </span>
        }
        right={
          <div className="flex items-center gap-2">
            <PublicHeaderLink href="/privacy">Privacidad</PublicHeaderLink>
            <PublicHeaderLink href="/terms">Términos</PublicHeaderLink>
          </div>
        }
      />

      <article className="relative z-10 mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
        <h1 className="font-[family-name:var(--font-orbitron)] text-xl font-bold tracking-wide text-cyan-200 sm:text-2xl">
          {title}
        </h1>
        <p className="mt-2 text-sm text-cyan-500/80">{updated}</p>
        <div className="mt-8 space-y-8 text-[14px] leading-relaxed text-cyan-100/90 [&_h2]:font-[family-name:var(--font-orbitron)] [&_h2]:text-[13px] [&_h2]:font-semibold [&_h2]:tracking-wide [&_h2]:text-cyan-300 [&_ul]:mt-3 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5 [&_p]:mt-3">
          {children}
        </div>
        <p className="mt-12 border-t border-cyan-900/50 pt-6 text-center text-[12px] text-cyan-600">
          <Link href="/" className="text-cyan-400 hover:text-cyan-200">
            Volver a CED
          </Link>
          {" · "}
          <Link href="/privacy" className="text-cyan-400 hover:text-cyan-200">
            Privacidad
          </Link>
          {" · "}
          <Link href="/terms" className="text-cyan-400 hover:text-cyan-200">
            Términos
          </Link>
        </p>
      </article>
    </main>
  );
}
