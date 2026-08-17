"use client";

import { useCedTheme } from "@/contexts/CedThemeContext";
import type { CedTheme } from "@/lib/theme/cedTheme";

const OPTIONS: Array<{ id: CedTheme; label: string; hint: string }> = [
  {
    id: "petrol",
    label: "Oscuro",
    hint: "Fondo petróleo, tono Gemini. El chat sigue blanco.",
  },
  {
    id: "light",
    label: "Claro",
    hint: "Menú y tarjetas claras, como ahora.",
  },
];

export function ThemeAppearanceToggle() {
  const { theme, setTheme } = useCedTheme();

  return (
    <section className="ced-gold-outline rounded-xl bg-[var(--ced-surface)]/40 p-4">
      <h2 className="font-[family-name:var(--font-orbitron)] text-xs tracking-wider text-[var(--ced-cyan)]">
        APARIENCIA
      </h2>
      <p className="mt-1 mb-3 text-xs text-[var(--ced-text-muted)]">
        Oscuro en toda la app; el panel de texto permanece blanco.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {OPTIONS.map((option) => {
          const active = theme === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setTheme(option.id)}
              className={`ced-gold-outline rounded-xl px-3 py-2.5 text-left text-xs transition ${
                active
                  ? "bg-[var(--ced-cyan)]/20 text-[var(--ced-text-primary)]"
                  : "bg-black/20 text-[var(--ced-text-muted)] hover:bg-[var(--ced-cyan)]/10"
              }`}
            >
              <div className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-wider uppercase">
                {option.label}
              </div>
              <p className="mt-1 text-[10px] leading-snug opacity-80">{option.hint}</p>
            </button>
          );
        })}
      </div>
    </section>
  );
}
