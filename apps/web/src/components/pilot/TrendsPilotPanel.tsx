"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
  TRENDS_WELCOME,
  analyzeTrends,
  fetchTrendsPilotStatus,
  type TrendsFinding,
  type TrendsReport,
} from "@/lib/api/trendsPilot";
import type { ModulePanelProps } from "@/modules/types";

function FindingList({
  title,
  items,
  empty,
}: {
  title: string;
  items: TrendsFinding[];
  empty: string;
}) {
  return (
    <section>
      <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-cyan-300/90">
        {title}
      </h3>
      {items.length > 0 ? (
        <ul className="space-y-3">
          {items.slice(0, 4).map((f, i) => (
            <li
              key={`${f.text.slice(0, 40)}-${i}`}
              className="rounded-xl border border-white/10 bg-black/30 px-3.5 py-2.5"
            >
              <div className="text-sm leading-relaxed text-slate-300">{f.text}</div>
              {f.source_url ? (
                <a
                  href={f.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-0.5 block truncate text-[10px] text-cyan-500/80 hover:underline"
                >
                  {f.source_title || f.source_url}
                </a>
              ) : f.source_title ? (
                <div className="mt-0.5 text-[10px] text-slate-500">{f.source_title}</div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">{empty}</p>
      )}
    </section>
  );
}

function ReportView({ report }: { report: TrendsReport }) {
  const outlook = report.outlook_6m;
  return (
    <div className="space-y-6 text-[14px] leading-[1.65] text-slate-200">
      {report.profile?.anchor ? (
        <section className="rounded-xl border border-white/10 bg-black/25 px-3.5 py-2.5 text-sm">
          Ancla de búsqueda:{" "}
          <span className="text-cyan-100">{report.profile.anchor}</span>
          {report.profile.category || report.profile.industry_label ? (
            <span className="text-slate-500">
              {" "}
              · {report.profile.category || report.profile.industry_label}
            </span>
          ) : null}
        </section>
      ) : null}

      <FindingList
        title="Trending ahora (búsqueda)"
        items={report.trending_now || []}
        empty="Sin señales de trending atribuibles en esta sesión."
      />
      <FindingList
        title="Necesidades emergentes (búsqueda)"
        items={report.consumer_needs || []}
        empty="Sin necesidades emergentes con fuente en esta sesión."
      />

      <section>
        <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-amber-300/90">
          Outlook ~6 meses
          <span className="ml-1 font-normal normal-case text-slate-500">
            ({outlook?.attribution === "search" ? "búsqueda" : "razonamiento"})
          </span>
        </h3>
        {outlook?.attribution === "search" && (outlook.findings || []).length > 0 ? (
          <ul className="space-y-3">
            {(outlook.findings || []).slice(0, 3).map((f, i) => (
              <li
                key={`out-${i}`}
                className="rounded-xl border border-white/10 bg-black/30 px-3.5 py-2.5 text-sm leading-relaxed text-slate-300"
              >
                {f.text}
                {f.source_url ? (
                  <a
                    href={f.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-0.5 block truncate text-[10px] text-cyan-500/80 hover:underline"
                  >
                    {f.source_title || f.source_url}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-3.5 py-2.5 text-sm leading-relaxed text-amber-100/90">
            {outlook?.model_note ||
              "Sin forecast en búsqueda — razonamiento etiquetado pendiente."}
          </p>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-violet-300/90">
          Oportunidades
        </h3>
        <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-slate-300">
          {(report.opportunities || []).map((o) => (
            <li key={o.idea}>
              <span className="text-[9px] uppercase text-slate-500">
                [{o.attribution || "model_reasoning"}]
              </span>{" "}
              {o.idea}
            </li>
          ))}
        </ol>
      </section>

      {(report.data_gaps || []).length > 0 ? (
        <section className="rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1.5">
          <h3 className="mb-1 text-[11px] font-semibold text-amber-200">
            Limitaciones de datos
          </h3>
          <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-amber-100/80">
            {(report.data_gaps || []).map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function TrendsModuleContent(_props: ModulePanelProps) {
  const [description, setDescription] = useState("");
  const [region, setRegion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<TrendsReport | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    void fetchTrendsPilotStatus().then((s) => setConfigured(s?.enabled ?? null));
  }, []);

  const submit = async () => {
    if (busy) return;
    if (!description.trim()) {
      setError("Describa su rubro o industria.");
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const result = await analyzeTrends({
        description: description.trim(),
        region: region.trim() || undefined,
      });
      setReport(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al analizar.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-8 sm:py-6">
        <p className="text-sm leading-relaxed text-slate-400">{TRENDS_WELCOME}</p>
        {configured === false ? (
          <p className="text-sm text-red-300">
            TRENDS_MODULE_PILOT desactivado en la API.
          </p>
        ) : null}

        <label className="block text-[11px] uppercase tracking-[0.08em] text-slate-500">
          Rubro / industria
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder='Ej: vendo suplementos alimenticios FitLine / tengo una cafetería de especialidad…'
            className="mt-2 w-full resize-none rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-sm leading-relaxed text-slate-100 outline-none focus:border-cyan-500/50"
          />
        </label>

        <label className="block text-[11px] uppercase tracking-[0.08em] text-slate-500">
          Región (opcional)
          <input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="Ej: Estados Unidos / CDMX"
            className="mt-2 w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-500/50"
          />
        </label>

        {error ? <p className="text-sm text-red-400">{error}</p> : null}
        {report ? <ReportView report={report} /> : null}
      </div>

      <footer className="border-t border-white/10 px-5 py-4 sm:px-8">
        <button
          type="button"
          disabled={busy}
          onClick={() => void submit()}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-600/90 px-4 py-3 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-60"
        >
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Buscando tendencias…
            </>
          ) : (
            "Analizar tendencias"
          )}
        </button>
      </footer>
    </div>
  );
}
