"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export interface CedButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
  fullWidth?: boolean;
}

const variantClass: Record<Variant, string> = {
    primary:
    "ced-gold-outline border-2 bg-[var(--ced-cyan)]/15 text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/30 ced-glow",
  secondary:
    "border border-[var(--ced-cyan)]/80 bg-transparent text-[var(--ced-cyan)] hover:border-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/10",
  ghost: "border border-transparent text-[var(--ced-cyan)]/80 hover:text-[var(--ced-cyan)] hover:bg-[var(--ced-cyan)]/5",
  danger:
    "border-2 border-red-500/70 bg-red-500/10 text-red-300 hover:bg-red-500/20",
};

export function CedButton({
  variant = "primary",
  fullWidth,
  className = "",
  children,
  type = "button",
  ...props
}: CedButtonProps) {
  return (
    <button
      type={type}
      className={[
        "font-[family-name:var(--font-orbitron)] text-xs font-bold tracking-widest uppercase",
        "rounded px-6 py-3 transition disabled:opacity-50 disabled:cursor-not-allowed",
        variantClass[variant],
        fullWidth ? "w-full" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    >
      {children}
    </button>
  );
}
