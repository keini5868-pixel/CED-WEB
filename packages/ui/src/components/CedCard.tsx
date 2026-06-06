import type { ReactNode } from "react";

export interface CedCardProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

/** Card premium — fondo negro sólido, borde cyan (sin patrón sobre texto). */
export function CedCard({ title, children, className = "" }: CedCardProps) {
  return (
    <section
      className={[
        "rounded border border-cyan-500/40 bg-[#0a0a0a] p-4 text-[#e0e0e0] ced-panel-glow",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {title ? (
        <h3 className="mb-3 font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-[0.18em] text-[#00e5ff] uppercase">
          {title}
        </h3>
      ) : null}
      {children}
    </section>
  );
}
