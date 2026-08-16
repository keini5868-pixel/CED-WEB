"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { HistorialArchivos } from "@/components/historial/HistorialArchivos";
import { HistorialConversaciones } from "@/components/historial/HistorialConversaciones";
import { HistorialPapelera } from "@/components/trash/HistorialPapelera";

type HistorialTab = "conversaciones" | "archivos" | "papelera";

export function HistorialHub() {
  const params = useSearchParams();
  const router = useRouter();
  const tab: HistorialTab =
    params.get("tab") === "archivos"
      ? "archivos"
      : params.get("tab") === "papelera"
        ? "papelera"
        : "conversaciones";

  function setTab(next: HistorialTab) {
    const path =
      next === "archivos"
        ? "/historial?tab=archivos"
        : next === "papelera"
          ? "/historial?tab=papelera"
          : "/historial";
    router.replace(path, { scroll: false });
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-[family-name:var(--font-orbitron)] text-lg font-bold text-cyan-300">
            HISTORIAL
          </h1>
          <p className="ced-hud-text-muted mt-1 text-sm">
            Conversaciones, imágenes y PDFs generados.
          </p>
        </div>
        <Link
          href="/dashboard"
          className="text-xs text-cyan-600 hover:text-cyan-400"
        >
          ← Dashboard
        </Link>
      </div>

      <div className="mb-6 flex gap-2 border-b border-cyan-900/40 pb-2">
        <button
          type="button"
          onClick={() => setTab("conversaciones")}
          className={[
            "rounded px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider",
            tab === "conversaciones"
              ? "bg-cyan-400/15 text-cyan-100"
              : "text-cyan-500 hover:text-cyan-200",
          ].join(" ")}
        >
          Conversaciones
        </button>
        <button
          type="button"
          onClick={() => setTab("archivos")}
          className={[
            "rounded px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider",
            tab === "archivos"
              ? "bg-cyan-400/15 text-cyan-100"
              : "text-cyan-500 hover:text-cyan-200",
          ].join(" ")}
        >
          Imágenes y PDF
        </button>
        <button
          type="button"
          onClick={() => setTab("papelera")}
          className={[
            "rounded px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider",
            tab === "papelera"
              ? "bg-cyan-400/15 text-cyan-100"
              : "text-cyan-500 hover:text-cyan-200",
          ].join(" ")}
        >
          Papelera
        </button>
      </div>

      {tab === "papelera" ? (
        <HistorialPapelera />
      ) : tab === "archivos" ? (
        <HistorialArchivos />
      ) : (
        <HistorialConversaciones embedded />
      )}
    </div>
  );
}
