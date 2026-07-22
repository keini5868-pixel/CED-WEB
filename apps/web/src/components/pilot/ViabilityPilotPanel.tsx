"use client";

import { ImagePlus, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  VIABILITY_WELCOME,
  analyzeViability,
  fetchViabilityPilotStatus,
  type ViabilityReport,
} from "@/lib/api/viabilityPilot";
import type { ModulePanelProps } from "@/modules/types";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const b64 = result.includes(",")
        ? (result.split(",", 2)[1] ?? result)
        : result;
      resolve(b64);
    };
    reader.onerror = () => reject(new Error("No se pudo leer la imagen"));
    reader.readAsDataURL(file);
  });
}

function ReportView({ report }: { report: ViabilityReport }) {
  const likelihood = report.likelihood;
  const profile = report.offering_profile;
  return (
    <div className="space-y-4 text-[12px] leading-relaxed text-slate-200">
      {profile?.product_name || profile?.channel ? (
        <section className="rounded border border-white/10 bg-black/25 px-2 py-1.5 text-[11px] text-slate-300">
          {profile.product_name ? (
            <div>
              Producto ancla:{" "}
              <span className="text-cyan-100">{profile.product_name}</span>
              {profile.brand ? (
                <span className="text-slate-500"> · {profile.brand}</span>
              ) : null}
            </div>
          ) : null}
          {profile.channel ? (
            <div className="text-[10px] text-slate-500">
              Canal: {profile.channel}
              {profile.category ? ` · ${profile.category}` : ""}
            </div>
          ) : null}
        </section>
      ) : null}
      {likelihood ? (
        <section>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-amber-300/90">
            Probabilidad orientativa
          </h3>
          <p className="text-sm text-amber-100">
            {likelihood.range} — {likelihood.label}
          </p>
          <p className="mt-1 text-[11px] text-slate-400">
            {likelihood.rationale}
            <span className="ml-1 text-slate-500">
              (razonamiento — no métrica verificada)
            </span>
          </p>
        </section>
      ) : null}

      <section>
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-cyan-300/90">
          Hallazgos de búsqueda
        </h3>
        {(report.competitors || []).length > 0 ? (
          <ul className="space-y-2">
            {(report.competitors || []).slice(0, 3).map((c) => (
              <li
                key={c.name}
                className="rounded border border-white/10 bg-black/30 px-2 py-1.5"
              >
                <div className="font-medium text-cyan-100">{c.name}</div>
                {c.competition_basis ? (
                  <div className="text-[10px] text-emerald-300/90">
                    Por qué compite: {c.competition_basis}
                  </div>
                ) : null}
                <div className="text-[11px] text-slate-400">{c.note}</div>
                {c.source_url ? (
                  <a
                    href={c.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-0.5 block truncate text-[10px] text-cyan-500/80 hover:underline"
                  >
                    {c.source_title || c.source_url}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[11px] text-slate-500">
            Sin competidores verificables en esta sesión.
          </p>
        )}

        {(report.pricing?.findings || []).length > 0 ? (
          <div className="mt-3">
            <div className="mb-1 text-[10px] uppercase text-slate-500">
              Precios en resultados
            </div>
            <ul className="space-y-1">
              {(report.pricing?.findings || []).slice(0, 4).map((p, i) => (
                <li key={`${p.text}-${i}`} className="text-[11px] text-slate-300">
                  <span className="text-emerald-300">{p.text}</span>
                  {p.context ? ` — ${p.context.slice(0, 100)}` : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-2 text-[11px] text-slate-500">
            Sin precios atribuibles en los resultados.
          </p>
        )}
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

      {report.search_meta &&
      (report.search_meta.sources === 0 ||
        report.search_meta.rate_limited ||
        report.search_meta.missing_key ||
        (report.search_meta.errors && report.search_meta.errors.length > 0)) ? (
        <p className="text-[10px] text-slate-500">
          Diagnóstico búsqueda: sources={report.search_meta.sources ?? 0}
          {report.search_meta.rate_limited ? " · rate-limited" : ""}
          {report.search_meta.fallback_used ? " · fallback EN" : ""}
          {(report.search_meta.errors?.length || 0) > 0
            ? ` · errores=${report.search_meta.errors?.length}`
            : ""}
        </p>
      ) : null}

      <section>
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-violet-300/90">
          Ideas de mejora
          <span className="ml-1 font-normal normal-case text-slate-500">
            (razonamiento general)
          </span>
        </h3>
        <ol className="list-decimal space-y-1 pl-4 text-[11px] text-slate-300">
          {(report.improvements || []).map((idea) => (
            <li key={idea.idea}>{idea.idea}</li>
          ))}
        </ol>
      </section>
    </div>
  );
}

/**
 * Contenido del módulo para el shell lateral.
 * Estado local — se descarta al desmontar (cerrar drawer).
 */
export function ViabilityModuleContent(_props: ModulePanelProps) {
  const [description, setDescription] = useState("");
  const [region, setRegion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ViabilityReport | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [imageB64, setImageB64] = useState<string | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void fetchViabilityPilotStatus().then((s) => {
      setConfigured(s?.enabled ?? null);
    });
  }, []);

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const onFile = async (file: File | null) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Solo imágenes (flyer o foto del producto).");
      return;
    }
    try {
      const b64 = await fileToBase64(file);
      setImageB64(b64);
      setPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(file);
      });
      setError(null);
    } catch {
      setError("No se pudo cargar la imagen.");
    }
  };

  const submit = async () => {
    if (busy) return;
    if (!description.trim() && !imageB64) {
      setError("Escriba una descripción o suba un flyer/foto.");
      return;
    }
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const result = await analyzeViability({
        description: description.trim() || undefined,
        imageBase64: imageB64 || undefined,
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
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        <p className="text-[11px] text-slate-400">{VIABILITY_WELCOME}</p>
        {configured === false ? (
          <p className="text-[11px] text-red-300">
            El flag de API tiene el módulo desactivado (VIABILITY_MODULE_PILOT).
          </p>
        ) : null}

        <label className="block text-[10px] uppercase text-slate-500">
          Descripción del producto / servicio
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Ej: Cafetería de especialidad en Santo Domingo con suscripción mensual de café..."
            className="mt-1 w-full resize-none rounded border border-white/15 bg-black/40 px-3 py-2 text-[12px] text-slate-100 outline-none focus:border-cyan-500/50"
          />
        </label>

        <label className="block text-[10px] uppercase text-slate-500">
          Región (opcional)
          <input
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="Ej: República Dominicana / CDMX"
            className="mt-1 w-full rounded border border-white/15 bg-black/40 px-3 py-2 text-[12px] text-slate-100 outline-none focus:border-cyan-500/50"
          />
        </label>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="inline-flex items-center gap-1.5 rounded border border-white/15 bg-white/5 px-3 py-1.5 text-[11px] text-slate-200 hover:bg-white/10"
          >
            <ImagePlus className="h-3.5 w-3.5" />
            Subir flyer / foto
          </button>
          {preview ? (
            <button
              type="button"
              className="text-[10px] text-slate-500 hover:text-slate-300"
              onClick={() => {
                setPreview((prev) => {
                  if (prev) URL.revokeObjectURL(prev);
                  return null;
                });
                setImageB64(null);
              }}
            >
              Quitar imagen
            </button>
          ) : null}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => void onFile(e.target.files?.[0] ?? null)}
          />
        </div>
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={preview}
            alt="Vista previa"
            className="max-h-36 rounded border border-white/10 object-contain"
          />
        ) : null}

        {error ? <p className="text-[11px] text-red-400">{error}</p> : null}
        {report ? <ReportView report={report} /> : null}
      </div>

      <footer className="border-t border-white/10 px-4 py-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => void submit()}
          className="inline-flex w-full items-center justify-center gap-2 rounded bg-cyan-600/90 px-3 py-2.5 text-[12px] font-semibold text-white hover:bg-cyan-500 disabled:opacity-60"
        >
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Buscando mercado y sintetizando…
            </>
          ) : (
            "Analizar viabilidad"
          )}
        </button>
      </footer>
    </div>
  );
}
