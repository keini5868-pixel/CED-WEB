"use client";

import type { InputHTMLAttributes } from "react";

export interface CedInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function CedInput({
  label,
  error,
  className = "",
  id,
  ...props
}: CedInputProps) {
  const inputId = id || props.name;
  return (
    <div className="w-full">
      {label ? (
        <label
          htmlFor={inputId}
          className="mb-2 block font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest text-cyan-500 uppercase"
        >
          {label}
        </label>
      ) : null}
      <input
        id={inputId}
        className={[
          "ced-input-animated ced-gold-outline w-full rounded-xl bg-black/50 px-4 py-3",
          "font-[family-name:var(--font-inter)] text-sm text-cyan-100",
          "placeholder:text-cyan-800 focus:outline-none focus:ring-1 focus:ring-[var(--ced-gold)]/50",
          error ? "border-red-500/60" : "",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...props}
      />
      {error ? (
        <p className="mt-2 text-xs text-red-400">{error}</p>
      ) : null}
    </div>
  );
}
