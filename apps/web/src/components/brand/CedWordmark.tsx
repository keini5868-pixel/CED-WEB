import type { ReactNode } from "react";

type CedWordmarkSize = "sm" | "md" | "lg" | "orb";

const SIZE: Record<CedWordmarkSize, string> = {
  sm: "text-xs sm:text-sm tracking-[0.14em]",
  md: "text-lg tracking-[0.16em]",
  lg: "text-3xl sm:text-4xl tracking-[0.16em]",
  orb: "text-[1.65rem] tracking-[0.1em] md:text-[1.85rem]",
};

/**
 * Marca CED — Orbitron con tracking corto para que la D no se lea como O.
 */
export function CedWordmark({
  size = "md",
  glow = true,
  tone = "cyan",
  className = "",
  children = "CED",
}: {
  size?: CedWordmarkSize;
  glow?: boolean;
  tone?: "cyan" | "white";
  className?: string;
  children?: ReactNode;
}) {
  return (
    <span
      className={[
        "font-[family-name:var(--font-orbitron)] font-bold",
        tone === "white" ? "text-white" : "text-cyan-300",
        SIZE[size],
        glow ? "ced-glow-text" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </span>
  );
}
