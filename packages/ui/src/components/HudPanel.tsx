"use client";

import type { ReactNode } from "react";

export interface HudPanelProps {
  title: string;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  state?: "idle" | "searching" | "receiving" | "complete";
}

const stateBorder: Record<NonNullable<HudPanelProps["state"]>, string> = {
  idle: "border-cyan-500/45",
  searching: "border-amber-400/60 animate-pulse",
  receiving: "border-cyan-400/80",
  complete: "border-cyan-400/55",
};

/**
 * Panel HUD — texto sobre fondo negro sólido.
 * Líneas decorativas solo en borde; sin patrón sobre el contenido.
 */
export function HudPanel({
  title,
  children,
  className = "",
  bodyClassName = "",
  state = "idle",
}: HudPanelProps) {
  return (
    <section
      className={[
        "ced-hud-panel relative isolate flex flex-col overflow-hidden rounded border bg-black",
        stateBorder[state],
        "ced-panel-glow",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {/* Acento decorativo en esquinas del marco (no cruza el contenido) */}
      <div
        className="pointer-events-none absolute inset-0 z-0 rounded-[inherit]"
        aria-hidden
        style={{
          background: `
            linear-gradient(90deg, rgba(0,229,255,0.35) 0%, transparent 12%) top left / 100% 1px no-repeat,
            linear-gradient(90deg, transparent 88%, rgba(0,229,255,0.35) 100%) bottom right / 100% 1px no-repeat,
            linear-gradient(0deg, rgba(0,229,255,0.25) 0%, transparent 10%) top left / 1px 100% no-repeat,
            linear-gradient(0deg, transparent 90%, rgba(0,229,255,0.25) 100%) bottom right / 1px 100% no-repeat
          `,
        }}
      />

      <header className="relative z-10 shrink-0 border-b border-cyan-500/30 bg-[#0a0a0a] px-4 py-2.5">
        <h3 className="font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-[0.18em] text-[#00e5ff] uppercase">
          {title}
        </h3>
      </header>

      <div
        className={[
          "ced-hud-panel-body relative z-10 min-h-0 flex-1 overflow-hidden bg-black p-4 text-sm leading-relaxed text-[#e0e0e0]",
          bodyClassName,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {children}
      </div>
    </section>
  );
}
