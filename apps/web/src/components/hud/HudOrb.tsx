"use client";

/** Orbe central con anillos — placeholder Three.js en Fase 2. */
export function HudOrb() {
  return (
    <div className="relative flex h-40 w-40 items-center justify-center md:h-52 md:w-52">
      <div className="absolute inset-0 animate-spin rounded-full border border-cyan-500/20 [animation-duration:12s]" />
      <div className="absolute inset-3 animate-spin rounded-full border border-dashed border-cyan-400/30 [animation-duration:8s] [animation-direction:reverse]" />
      <div className="absolute inset-6 rounded-full border-2 border-cyan-400/50 ced-glow" />
      <span className="relative font-[family-name:var(--font-orbitron)] text-2xl font-bold text-cyan-300 ced-glow-text md:text-3xl">
        CED
      </span>
      <p className="ced-hud-text-muted absolute -bottom-6 w-full text-center font-[family-name:var(--font-orbitron)] text-xs tracking-widest uppercase">
        IDLE
      </p>
    </div>
  );
}
