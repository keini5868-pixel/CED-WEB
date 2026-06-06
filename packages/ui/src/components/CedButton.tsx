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
    "border-2 border-cyan-400 bg-cyan-400/15 text-cyan-200 hover:bg-cyan-400/30 ced-glow",
  secondary:
    "border border-cyan-600/80 bg-transparent text-cyan-400 hover:border-cyan-400 hover:bg-cyan-400/10",
  ghost: "border border-transparent text-cyan-500 hover:text-cyan-300 hover:bg-cyan-400/5",
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
