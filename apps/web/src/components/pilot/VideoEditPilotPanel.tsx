"use client";

import { Clapperboard, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  checkoutVideoEditPack,
  fetchVideoEditBalance,
  quoteVideoEdit,
  renderVideoEdit,
  type VideoEditBalance,
  type VideoEditQuote,
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

  const refresh = useCallback(async () => {
    const bal = await fetchVideoEditBalance();
    setBalance(bal);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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

  const onPickFile = async (f: File | null) => {
    setError(null);
    setMessage(null);
    setTimelinePreview(null);
    setResultUrl(null);
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
    try {
      const result = await renderVideoEdit({
        duration_sec: durationSec || 30,
        script,
        file,
      });
      if (!result.ok) {
        setError(
          result.message ||
            result.error ||
            "No se pudo editar el video.",
        );
        await refresh();
        return;
      }
      setMessage(
        result.message ||
          `Listo. Cobrado ${result.tokens_charged ?? "?"} tokens.`,
      );
      if (result.result_url) {
        setResultUrl(result.result_url);
      }
      if (result.timeline) {
        setTimelinePreview(JSON.stringify(result.timeline, null, 2));
      }
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

  const packs = useMemo(() => balance?.packs ?? [], [balance]);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-1 pb-8 pt-2">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-cyan-200">
          <Clapperboard className="h-5 w-5" />
          <h2 className="text-lg font-semibold tracking-tight">
            Edición de video
          </h2>
        </div>
        <p className="text-sm text-slate-400">
          Sube tu video + guion. Cobramos por segundos reales:{" "}
          <span className="text-slate-200">1 segundo = 1 token</span>, mínimo 30
          s. Soft cap: {balance?.soft_cap_per_day ?? 10} renders/día.
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
              <span className="text-sm font-normal text-slate-400">tokens</span>
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
            rows={6}
            placeholder="Escriba el guion por escenas. CED ubicará cortes, transiciones y efectos de sonido (Text→SFX)."
            className="w-full resize-y rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/40 focus:outline-none"
          />
        </label>

        <button
          type="button"
          disabled={busy || !file || !script.trim() || durationSec <= 0}
          onClick={() => void onRender()}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-cyan-500/90 px-4 py-2.5 text-sm font-medium text-black hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {busy ? "Procesando en Shotstack…" : "Generar edición"}
        </button>
        <p className="text-[11px] text-slate-500">
          Si cambió de pestaña, vuelva a elegir el MP4 antes de generar. El render
          en vivo puede tardar 1–3 minutos.
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
      {resultUrl ? (
        <section className="space-y-2 rounded-xl border border-cyan-500/30 bg-black/40 px-3 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-cyan-300/90">
            Video editado
          </p>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video
            src={resultUrl}
            controls
            className="max-h-80 w-full rounded-lg bg-black object-contain"
          />
          <a
            href={resultUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-sm text-cyan-300 underline hover:text-cyan-200"
          >
            Abrir / descargar MP4
          </a>
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
  );
}

export default VideoEditModuleContent;
