"use client";

import type { ReactNode } from "react";
import { useState } from "react";

export function HudCollapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="overflow-hidden rounded border border-cyan-500/45 bg-[#000000] ced-panel-glow lg:hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between border-b border-cyan-500/30 bg-[#0a0a0a] px-4 py-3"
      >
        <span className="font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-[0.18em] text-[var(--ced-cyan)] uppercase">
          {title}
        </span>
        <span className="text-base font-bold text-[#4dd0e1]" aria-hidden>
          {open ? "−" : "+"}
        </span>
      </button>
      {open ? (
        <div className="bg-[#0a0a0a] p-4 text-sm leading-relaxed text-[#e0e0e0]">
          {children}
        </div>
      ) : null}
    </div>
  );
}
