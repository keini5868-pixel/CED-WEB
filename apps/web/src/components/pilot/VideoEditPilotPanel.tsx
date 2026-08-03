"use client";

import { Clapperboard, Expand, Loader2, Maximize2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  checkoutVideoEditPack,
  fetchVideoEditBalance,
  loadPendingVideoEditJob,
  pollVideoEditJob,
  quoteVideoEdit,
  renderVideoEdit,
  savePendingVideoEditJob,
  type VideoEditBalance,
  type VideoEditQuote,
  type VideoEditRenderResult,
} from "@/lib/api/videoEditPilot";
import type { ModulePanelProps } from "@/modules/types";

function readVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      const d = Number(video.duration) || 0;
      URL.revokeObjectURL(url);
      resolve(d);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("No se pudo leer la duración del video"));
    };
    video.src = url;
  });
}

/** Panel piloto — estado se descarta al desmontar (cerrar drawer). */
export function VideoEditModuleContent(_props: ModulePanelProps) {
  const [balance, setBalance] = useState<VideoEditBalance | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [durationSec, setDurationSec] = useState(0);
  const [script, setScript] = useState("");
  const [quote, setQuote] = useState<VideoEditQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timelinePreview, setTimelinePreview] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [editSummary, setEditSummary] = useState<string | null>(null);
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const resultRef = useRef<HTMLElement | null>(null);

  const refresh = useCallback(async () => {
    const bal = await fetchVideoEditBalance();
    setBalance(bal);
  }, []);

  const applyResult = useCallback((result: VideoEditRenderResult) => {
    setMessage(
      result.message ||
        `Listo. Cobrado ${result.tokens_charged ?? "?"} tokens.`,
    );
    if (result.result_url) {
      setResultUrl(result.result_url);
    }
    if (result.timeline) {
      const tl = result.timeline as {
        scenes?: unknown[];
        style_mood?: string;
      };
      const n = Array.isArray(tl.scenes) ? tl.scenes.length : 0;
      const mood = tl.style_mood || "estilo";
      setEditSummary(
        n > 1
          ? `Edición aplicada: ${n} cortes (${mood}). Marca SHOTSTACK = entorno stage (normal).`
          : "Render listo. Tip: usa palabras como “suspenso” o “acción” para cortes visibles.",
      );
      setTimelinePreview(JSON.stringify(result.timeline, null, 2));
    }
  }, []);

  const resumeJob = useCallback(
    async (jobId: string) => {
      setBusy(true);
      setError(null);
      setPendingJobId(jobId);
      setMessage("Retomando render en curso… puede tardar varios minutos.");
      try {
        const result = await pollVideoEditJob(jobId, undefined, {
          onTick: (r) => {
            if (r.message) setMessage(r.message);
          },
        });
        if (result.code === "still_rendering") {
          setPendingJobId(result.job_id || jobId);
          setError(result.message || "Sigue renderizando.");
          setMessage(null);
          return;
        }
        if (!result.ok) {
          setPendingJobId(null);
          setError(
            result.message || result.error || "No se pudo editar el video.",
          );
          await refresh();
          return;
        }
        setPendingJobId(null);
        applyResult(result);
        await refresh();
      } catch {
        setError("Error de red al consultar el render.");
      } finally {
        setBusy(false);
      }
    },
    [applyResult, refresh],
  );

  useEffect(() => {
    void refresh();
    const pending = loadPendingVideoEditJob();
    if (pending) {
      setPendingJobId(pending);
      void resumeJob(pending);
    }
  }, [refresh, resumeJob]);

  useEffect(() => {
    if (durationSec <= 0) {
      setQuote(null);
      return;
    }
    let cancelled = false;
    void quoteVideoEdit(durationSec).then((q) => {
      if (!cancelled) setQuote(q);
    });
    return () => {
      cancelled = true;
    };
  }, [durationSec]);

  useEffect(() => {
    if (!resultUrl) return;
    resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [resultUrl]);

  const onPickFile = async (f: File | null) => {
    setError(null);
    setMessage(null);
    setTimelinePreview(null);
    setResultUrl(null);
    setEditSummary(null);
    setFile(f);
    if (!f) {
      setDurationSec(0);
      return;
    }
    try {
      const d = await readVideoDuration(f);
      setDurationSec(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error leyendo video");
      setDurationSec(0);
    }
  };

  const onRender = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    setTimelinePreview(null);
    setResultUrl(null);
    setEditSummary(null);
    try {
      const result = await renderVideoEdit({
        duration_sec: durationSec || 30,
        script,
        file,
      });
      if (result.code === "still_rendering" && result.job_id) {
        setPendingJobId(result.job_id);
        savePendingVideoEditJob(result.job_id);
        setError(result.message || "Sigue renderizando.");
        setMessage(null);
        await refresh();
        return;
      }
      if (!result.ok) {
        setError(
          result.message ||
            result.error ||
            "No se pudo editar el video.",
        );
        await refresh();
        return;
      }
      setPendingJobId(null);
      applyResult(result);
      await refresh();
    } catch {
      setError("Error de red al procesar el video.");
    } finally {
      setBusy(false);
    }
  };

  const onBuy = async (amount: number) => {
    setCheckoutBusy(true);
    setError(null);
    try {
      const out = await checkoutVideoEditPack(amount);
      if (out.url) {
        window.location.href = out.url;
        return;
      }
      setError(out.error || "Checkout no disponible.");
    } finally {
      setCheckoutBusy(false);
    }
  };

  const onFullscreen = async () => {
    const el = videoRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }
      if (el.requestFullscreen) {
        await el.requestFullscreen();
      } else {
        const anyEl = el as HTMLVideoElement & {
          webkitEnterFullscreen?: () => void;
        };
        anyEl.webkitEnterFullscreen?.();
      }
    } catch {
      window.open(resultUrl || "", "_blank", "noopener,noreferrer");
    }
  };

  const packs = useMemo(() => balance?.packs ?? [], [balance]);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-y-contain px-4 py-4 pb-28 sm:px-6 sm:py-5">
        <header className="space-y-1">
          <div className="flex items-center gap-2 text-cyan-200">
            <Clapperboard className="h-5 w-5" />
            <h2 className="text-lg font-semibold tracking-tight">
              Edición de video
            </h2>
          </div>
          <p className="text-sm text-slate-400">
            Sube tu video + guion. Cobramos por segundos reales:{" "}
            <span className="text-slate-200">1 segundo = 1 token</span>, mínimo
            30 s. Soft cap: {balance?.soft_cap_per_day ?? 10} renders/día.
          </p>
        </header>

        <section className="rounded-xl border border-white/10 bg-black/30 px-4 py-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-500">
                Saldo
              </div>
              <div className="text-2xl font-semibold text-cyan-100">
                {balance?.balance_tokens ?? "—"}{" "}
                <span className="text-sm font-normal text-slate-400">
                  tokens
                </span>
              </div>
            </div>
            <div className="text-right text-xs text-slate-500">
              Renders hoy: {balance?.renders_today ?? 0}/
              {balance?.soft_cap_per_day ?? 10}
              <br />
              Restantes: {balance?.soft_cap_remaining ?? "—"}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {packs.map((p) => (
              <button
                key={p.amount_paid_usd}
                type="button"
                disabled={checkoutBusy}
                onClick={() => void onBuy(p.amount_paid_usd)}
                className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-sm text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-50"
              >
                ${p.amount_paid_usd} → {p.tokens} tokens
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-slate-500">
            $1 = 100 tokens · margen 30–35% sobre COGS · no expira
          </p>
        </section>

        <section className="space-y-3">
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-slate-300">
              Video
            </span>
            <input
              type="file"
              accept="video/*"
              className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-sm file:text-cyan-100"
              onChange={(e) => void onPickFile(e.target.files?.[0] ?? null)}
            />
            {durationSec > 0 ? (
              <p className="mt-1 text-xs text-slate-500">
                Duración detectada: {durationSec.toFixed(1)} s
                {quote
                  ? ` · Cobro: ${quote.tokens} tokens ($${quote.price_usd.toFixed(2)})`
                  : null}
              </p>
            ) : null}
          </label>

          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-slate-300">
              Guion
            </span>
            <textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              rows={4}
              placeholder={`0-8s: descripción
TRANSICIÓN: corte rápido
SONIDO: whoosh

8-18s: siguiente escena
TRANSICIÓN: corte seco
SONIDO: click`}
              className="w-full resize-y rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/40 focus:outline-none"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              Use rangos de tiempo (0-8s). El zoom de Shotstack se evita a
              propósito: recorta cara/cuerpo. Preferimos corte/fade + fit contain.
            </p>
          </label>

          <button
            type="button"
            disabled={busy || !file || !script.trim() || durationSec <= 0}
            onClick={() => void onRender()}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500/90 px-4 py-2.5 text-sm font-medium text-black hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {busy ? "Esperando Shotstack…" : "Generar edición"}
          </button>
          {pendingJobId && !busy ? (
            <button
              type="button"
              onClick={() => void resumeJob(pendingJobId)}
              className="ml-2 inline-flex items-center justify-center gap-2 rounded-xl border border-amber-400/50 bg-amber-500/15 px-4 py-2.5 text-sm font-medium text-amber-100 hover:bg-amber-500/25"
            >
              Seguir esperando
            </button>
          ) : null}
          <p className="text-[11px] text-slate-500">
            El render puede tardar varios minutos con varios cortes. Si aparece
            “sigue en curso”, use Seguir esperando — no genere otra vez.
          </p>
        </section>

        {error ? (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        ) : null}
        {message ? (
          <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
            {message}
          </p>
        ) : null}
        {editSummary ? (
          <p className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            {editSummary}
          </p>
        ) : null}

        {resultUrl ? (
          <section
            ref={resultRef}
            className="space-y-3 rounded-xl border border-cyan-500/30 bg-black/40 px-3 py-3"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium uppercase tracking-wide text-cyan-300/90">
                Video editado
              </p>
              <button
                type="button"
                onClick={() => void onFullscreen()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1.5 text-xs text-cyan-100 hover:bg-cyan-500/20"
              >
                <Maximize2 className="h-3.5 w-3.5" />
                Pantalla completa
              </button>
            </div>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video
              ref={videoRef}
              src={resultUrl}
              controls
              playsInline
              className="max-h-[min(55vh,420px)] w-full rounded-lg bg-black object-contain"
            />
            <div className="flex flex-wrap gap-3 text-sm">
              <a
                href={resultUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-cyan-300 underline hover:text-cyan-200"
              >
                <Expand className="h-3.5 w-3.5" />
                Abrir en pestaña nueva
              </a>
              <a
                href={resultUrl}
                download
                className="text-cyan-300 underline hover:text-cyan-200"
              >
                Descargar MP4
              </a>
            </div>
          </section>
        ) : null}

        {timelinePreview ? (
          <details className="rounded-xl border border-white/10 bg-black/40 px-3 py-2">
            <summary className="cursor-pointer text-xs text-slate-400">
              Timeline técnica
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto text-[11px] leading-relaxed text-slate-400">
              {timelinePreview}
            </pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}

export default VideoEditModuleContent;
