import Link from "next/link";
import type { ReactNode } from "react";

type PublicSiteHeaderProps = {
  left: ReactNode;
  center?: ReactNode;
  right: ReactNode;
};

/** Barra superior pública — fondo sólido, no invade la barra de estado del móvil. */
export function PublicSiteHeader({ left, center, right }: PublicSiteHeaderProps) {
  const hasCenter = center != null && center !== false && center !== "";
  return (
    <header className="ced-chrome-bar ced-public-header relative z-50 border-b border-cyan-500/20 px-4 sm:px-6">
      <div className="ced-public-header__nav flex min-h-[52px] items-center justify-between gap-3">
        <div className="min-w-0 shrink">{left}</div>
        {hasCenter ? (
          <div className="hidden shrink-0 px-2 text-center sm:block">{center}</div>
        ) : null}
        <div className="shrink-0">{right}</div>
      </div>
      {hasCenter ? (
        <div className="ced-public-header__title border-t border-cyan-900/40 py-2 text-center sm:hidden">
          {center}
        </div>
      ) : null}
    </header>
  );
}

export function PublicHeaderLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="inline-flex min-h-[48px] items-center px-1 text-xs font-medium tracking-wide text-cyan-400 hover:text-cyan-200"
    >
      {children}
    </Link>
  );
}

export function PublicHeaderText({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex min-h-[48px] items-center text-xs text-cyan-500">
      {children}
    </span>
  );
}
