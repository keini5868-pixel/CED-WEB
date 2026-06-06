"use client";

import { HudPanel } from "@ced/ui";

import { useHudPanels, hudStateLabel } from "@/contexts/HudPanelContext";

export function HudGlobalPanel() {
  const { global, lastQuery, hudState } = useHudPanels();

  return (
    <div className="space-y-3">
      <p className="ced-hud-text-secondary text-[10px] uppercase tracking-widest">
        {hudStateLabel(hudState)}
        {lastQuery ? ` · ${lastQuery.slice(0, 48)}` : ""}
      </p>
      {global.length === 0 ? (
        <p className="ced-hud-text-body">
          Pide a CED que busque en internet — el contexto global aparecerá aquí.
        </p>
      ) : (
        <ul className="max-h-[200px] space-y-2 overflow-y-auto pr-1">
          {global.map((item) => (
            <li
              key={item.id}
              className="rounded border border-cyan-500/25 bg-black/50 px-3 py-2"
            >
              <p className="font-[family-name:var(--font-orbitron)] text-[10px] text-cyan-400">
                {item.title}
              </p>
              <p className="ced-hud-text-body mt-1 text-xs leading-snug">
                {item.text}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function HudSummaryPanel() {
  const { summary, hudState, lastQuery } = useHudPanels();

  return (
    <div className="space-y-2">
      {lastQuery ? (
        <p className="ced-hud-text-secondary text-[10px] uppercase tracking-widest">
          Resumen · {hudStateLabel(hudState)}
        </p>
      ) : null}
      <p className="ced-hud-text-body whitespace-pre-wrap leading-relaxed">
        {summary ||
          "El resumen en streaming aparecerá aquí cuando CED busque en internet."}
      </p>
    </div>
  );
}

export function HudWavesPanel() {
  const { waves } = useHudPanels();

  if (waves.length === 0) {
    return (
      <p className="ced-hud-text-body">
        Métricas y datos numéricos de la búsqueda aparecerán aquí.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {waves.map((item) => (
        <li key={item.id} className="border-l-2 border-amber-400/60 pl-3">
          <p className="text-xs font-medium text-amber-200">{item.title}</p>
          <p className="ced-hud-text-body text-xs">{item.text}</p>
        </li>
      ))}
    </ul>
  );
}

/** Wrapper con estado visual del panel HUD. */
export function HudGlobalPanelFrame({ children }: { children: React.ReactNode }) {
  const { hudState } = useHudPanels();
  return (
    <HudPanel title="GLOBAL" state={hudState === "idle" ? "idle" : hudState}>
      {children}
    </HudPanel>
  );
}

export function HudSummaryPanelFrame({
  children,
}: {
  children: React.ReactNode;
}) {
  const { hudState } = useHudPanels();
  const state =
    hudState === "searching" || hudState === "receiving"
      ? hudState
      : hudState === "complete"
        ? "complete"
        : "idle";
  return (
    <HudPanel title="SUMMARY" state={state}>
      {children}
    </HudPanel>
  );
}
