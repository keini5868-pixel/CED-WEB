"use client";

import { useCallback, useEffect, useState } from "react";

import {
  adminUpdateInsightStatus,
  fetchAdminInsights,
  type InsightQuestion,
} from "@/lib/api/support";

type Props = {
  compact?: boolean;
};

export function AdminInsightForum({ compact = false }: Props) {
  const [items, setItems] = useState<InsightQuestion[]>([]);
  const [status, setStatus] = useState<"new" | "reviewed" | "archived" | "all">(
    "new",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const rows = await fetchAdminInsights({
        status,
        limit: compact ? 40 : 80,
      });
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setBusy(false);
    }
  }, [compact, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const mark = async (id: string, next: "reviewed" | "archived") => {
    try {
      await adminUpdateInsightStatus(id, next);
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo actualizar");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-amber-500/20 px-3 py-2">
        {(["new", "reviewed", "archived", "all"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            className={`rounded px-2 py-1 text-[10px] font-semibold uppercase tracking-wider ${
              status === s
                ? "bg-amber-500/25 text-amber-100"
                : "text-amber-500/70 hover:bg-amber-500/10"
            }`}
          >
            {s === "new" ? "Nuevas" : s === "reviewed" ? "Vistas" : s === "archived" ? "Archivo" : "Todas"}
          </button>
        ))}
        <button
          type="button"
          onClick={() => void load()}
          className="ml-auto text-[10px] text-amber-400/80 hover:text-amber-200"
        >
          {busy ? "…" : "Actualizar"}
        </button>
      </div>
      {error ? (
        <p className="px-3 py-2 text-xs text-red-400">{error}</p>
      ) : null}
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {items.length === 0 && !busy ? (
          <p className="text-xs text-amber-500/70">
            Sin preguntas capturadas en este filtro. CED guarda automáticamente
            dudas de todos los usuarios: FitLine/PM, uso de CED, respuestas débiles,
            leads calientes y clientes enfriándose.
          </p>
        ) : null}
        {items.map((item) => (
          <article
            key={item.id}
            className="rounded-lg border border-amber-500/20 bg-black/30 p-3"
          >
            <div className="mb-1 flex flex-wrap items-center gap-1.5">
              <span
                className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${
                  item.priority === "high"
                    ? "bg-rose-500/20 text-rose-200"
                    : "bg-amber-500/15 text-amber-200"
                }`}
              >
                {item.priority || "normal"}
              </span>
              <span className="text-[9px] text-amber-600">
                {item.channel || "chat"}
              </span>
              <span
                className="max-w-[160px] truncate text-[9px] text-amber-400/80"
                title={item.user_email || item.user_id || ""}
              >
                {item.user_label || "anónimo"}
              </span>
              {(item.tags || []).map((t) => (
                <span
                  key={t}
                  className="rounded bg-cyan-500/10 px-1.5 py-0.5 text-[9px] text-cyan-300"
                >
                  {t}
                </span>
              ))}
              {item.created_at ? (
                <span className="ml-auto text-[9px] text-amber-700">
                  {new Date(item.created_at).toLocaleString()}
                </span>
              ) : null}
            </div>
            <p className="text-sm text-amber-50/95">{item.question}</p>
            {item.assistant_preview ? (
              <p className="mt-1 line-clamp-2 text-[11px] text-amber-500/70">
                Resp. CED: {item.assistant_preview}
              </p>
            ) : null}
            {status === "new" || status === "all" ? (
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => void mark(item.id, "reviewed")}
                  className="rounded border border-emerald-500/40 px-2 py-1 text-[10px] text-emerald-200 hover:bg-emerald-500/10"
                >
                  Revisada
                </button>
                <button
                  type="button"
                  onClick={() => void mark(item.id, "archived")}
                  className="rounded border border-amber-500/30 px-2 py-1 text-[10px] text-amber-300 hover:bg-amber-500/10"
                >
                  Archivar
                </button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
