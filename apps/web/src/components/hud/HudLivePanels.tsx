"use client";

import { useCallback, useMemo, useState } from "react";

import { HudPanel } from "@ced/ui";

import { useHudFeed, type HudFeedItem } from "@/contexts/HudFeedContext";

function roleLabel(kind: HudFeedItem["kind"]): string {
  if (kind === "voice") return "Usted";
  if (kind === "report") return "CED";
  if (kind === "news") return "Intel";
  return "CED";
}

function formatTranscript(items: HudFeedItem[]): string {
  const chronological = [...items].reverse();
  return chronological
    .map((item) => `${roleLabel(item.kind)}: ${item.text}`)
    .join("\n\n");
}

export function HudGlobalPanel() {
  const { items } = useHudFeed();
  const [copied, setCopied] = useState(false);

  const transcript = useMemo(() => formatTranscript(items), [items]);
  const chronological = useMemo(() => [...items].reverse(), [items]);

  const copyAll = useCallback(async () => {
    if (!transcript.trim()) return;
    try {
      await navigator.clipboard.writeText(transcript);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }, [transcript]);

  return (
    <div className="flex min-h-[280px] flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="ced-hud-text-secondary text-[10px] uppercase tracking-widest">
          Diálogo en vivo · {chronological.length} turnos
        </p>
        <button
          type="button"
          onClick={() => void copyAll()}
          disabled={!transcript.trim()}
          className="rounded border border-cyan-500/40 px-2 py-1 font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-wider text-cyan-300 transition hover:border-cyan-400 disabled:opacity-40"
        >
          {copied ? "Copiado" : "Copiar todo"}
        </button>
      </div>

      {chronological.length === 0 ? (
        <p className="ced-hud-text-body text-sm leading-relaxed">
          Aquí aparecerá la conversación con CED en tiempo real. Active el micrófono y
          podrá leer y copiar cada respuesta.
        </p>
      ) : (
        <div
          className="max-h-[min(420px,50vh)] flex-1 overflow-y-auto rounded border border-cyan-500/20 bg-black/40 p-3"
          role="log"
          aria-live="polite"
          aria-label="Transcripción de la conversación con CED"
        >
          <div className="space-y-3">
            {chronological.map((item) => (
              <div key={item.id} className="group">
                <p className="font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-wider text-cyan-500/90">
                  {roleLabel(item.kind)}
                </p>
                <p className="ced-hud-text-body mt-1 select-text whitespace-pre-wrap text-sm leading-relaxed">
                  {item.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function HudSummaryPanel() {
  const { items } = useHudFeed();
  const lastReport = items.find((i) => i.kind === "report")?.text ?? "";

  return (
    <div className="space-y-2">
      <p className="ced-hud-text-secondary text-[10px] uppercase tracking-widest">
        Última respuesta CED
      </p>
      <p className="ced-hud-text-body whitespace-pre-wrap leading-relaxed">
        {lastReport || "La última respuesta de CED aparecerá aquí."}
      </p>
    </div>
  );
}

export function HudWavesPanel() {
  const { items } = useHudFeed();
  const stats = items.filter((i) => i.kind === "stat" || i.kind === "news").slice(0, 6);

  if (stats.length === 0) {
    return (
      <p className="ced-hud-text-body">
        Datos de búsquedas e intel aparecerán aquí durante la sesión.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {stats.map((item) => (
        <li key={item.id} className="border-l-2 border-amber-400/60 pl-3">
          <p className="ced-hud-text-body text-xs">{item.text}</p>
        </li>
      ))}
    </ul>
  );
}

/** Wrapper con estado visual del panel HUD. */
export function HudGlobalPanelFrame({ children }: { children: React.ReactNode }) {
  return (
    <HudPanel title="CONVERSACIÓN" state="idle">
      {children}
    </HudPanel>
  );
}

export function HudSummaryPanelFrame({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <HudPanel title="ÚLTIMA RESPUESTA" state="idle">
      {children}
    </HudPanel>
  );
}
