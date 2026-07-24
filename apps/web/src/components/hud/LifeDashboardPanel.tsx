"use client";

import { dispatchLifeChatPrompt } from "@/lib/lifeActions";
import { useHudLifeData, hasRealWeatherData } from "@/hooks/useHudLifeData";

const lifeBtnClass =
  "rounded border border-cyan-400/30 bg-transparent px-2 py-0.5 text-[10px] text-[#00ffff] transition hover:bg-cyan-400/10";

function LifeActionButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={lifeBtnClass}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}

function CompactLifeSection({
  icon,
  title,
  lines,
  actions,
}: {
  icon: string;
  title: string;
  lines: string[];
  actions?: React.ReactNode;
}) {
  return (
    <section className="rounded border border-cyan-900/40 bg-black/40 px-2.5 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[9px] font-medium uppercase tracking-wider text-cyan-400/90">
            {icon} {title}
          </p>
          <ul className="mt-1 space-y-0.5 text-[10px] text-cyan-100/85">
            {lines.slice(0, 2).map((line, i) => (
              <li key={`${title}-${i}`} className="truncate">
                {line}
              </li>
            ))}
          </ul>
        </div>
        {actions ? <div className="flex shrink-0 flex-col gap-0.5">{actions}</div> : null}
      </div>
    </section>
  );
}

export function LifeDashboardPanel() {
  const { data, loadingWeather, refresh } = useHudLifeData();

  const place = data.place || "Charlotte NC";
  const weatherReady = hasRealWeatherData(data.weather.lines);
  const weatherHeadline = weatherReady
    ? data.weather.lines[0] ?? "Charlotte NC"
    : loadingWeather
      ? "Cargando clima…"
      : "Charlotte NC";

  return (
    <div className="space-y-2">
      <header className="flex items-center justify-between gap-2 rounded border border-cyan-500/20 bg-cyan-950/15 px-2.5 py-1.5">
        <p className="font-[family-name:var(--font-orbitron)] text-[9px] tracking-wider text-cyan-300">
          📅 {data.date_label}
        </p>
        <div className="flex items-center gap-2">
          {loadingWeather ? (
            <span className="ced-hud-text-muted text-[8px] opacity-50">Clima en fondo</span>
          ) : (
            <span className="ced-hud-text-muted text-[8px] opacity-60">Auto</span>
          )}
          <LifeActionButton label="↻" onClick={() => void refresh()} />
        </div>
      </header>

      <div className="grid gap-2 sm:grid-cols-3">
        <CompactLifeSection
          icon="🌤️"
          title="CLIMA"
          lines={[weatherHeadline, ...(data.weather.lines.slice(1, 2) || [])]}
          actions={
            <LifeActionButton
              label="Pregunta"
              onClick={() =>
                dispatchLifeChatPrompt(`¿qué clima hay hoy en ${place}?`, "weather")
              }
            />
          }
        />
        <CompactLifeSection
          icon="🌬️"
          title="AIRE"
          lines={data.air_quality.lines}
          actions={
            <LifeActionButton
              label="Pregunta"
              onClick={() =>
                dispatchLifeChatPrompt(
                  `¿cómo está la calidad del aire en ${place} hoy?`,
                  "weather",
                )
              }
            />
          }
        />
        <CompactLifeSection
          icon="🌿"
          title="POLEN"
          lines={data.pollen.lines}
          actions={
            <LifeActionButton
              label="Pregunta"
              onClick={() =>
                dispatchLifeChatPrompt(
                  `¿cuáles son los niveles de polen en ${place} hoy?`,
                  "weather",
                )
              }
            />
          }
        />
      </div>
    </div>
  );
}
