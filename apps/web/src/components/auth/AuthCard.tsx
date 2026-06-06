import type { ReactNode } from "react";

export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="w-full max-w-md rounded border border-cyan-500/30 bg-black/55 p-8 ced-glow">
      <h1 className="text-center font-[family-name:var(--font-orbitron)] text-xl tracking-widest text-cyan-300">
        {title}
      </h1>
      {subtitle ? (
        <p className="mt-2 text-center text-xs text-cyan-600">{subtitle}</p>
      ) : null}
      <div className="mt-8">{children}</div>
    </div>
  );
}
