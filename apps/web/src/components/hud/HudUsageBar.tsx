"use client";

import { useUsageBalance } from "@/hooks/useUsageBalance";

export function HudUsageBar() {
  const { balance } = useUsageBalance(5000);
  const pct = Math.min(100, balance.percent);
  const warn = pct >= 80;
  const critical = pct >= 95 || balance.blocked;

  return (
    <div>
      <div className="ced-hud-text-primary flex flex-wrap items-center justify-between gap-2 font-medium">
        <span>
          {balance.used.toFixed(1)} / {balance.plan} min hoy
        </span>
        <span
          className={
            critical
              ? "text-red-400"
              : warn
                ? "text-amber-400"
                : "ced-hud-text-accent"
          }
        >
          {balance.blocked
            ? "Límite alcanzado"
            : warn
              ? "⚠ Uso elevado"
              : "💎 Comprar más tiempo"}
        </span>
      </div>
      <div className="mt-3 h-2.5 overflow-hidden rounded bg-[#1a1a1a]">
        <div
          className={`h-full transition-all duration-500 ${
            critical ? "bg-red-500" : warn ? "bg-amber-400" : "bg-[#00e5ff]"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="ced-hud-text-muted mt-2">
        Uso diario Gemini Live · {pct.toFixed(0)}%
      </p>
    </div>
  );
}
