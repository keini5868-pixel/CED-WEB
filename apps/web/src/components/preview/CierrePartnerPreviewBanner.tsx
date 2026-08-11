"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getPreviewPersona,
  isCierrePartnerPreview,
  setPreviewPersona,
  type PreviewPersona,
} from "@/lib/preview/cierrePartnerPreview";

/**
 * Visible junto a ADMIN (flag del servidor). No depende del hook cliente
 * (SUPER_ADMIN_EMAILS no se expone al browser).
 */
export function CierrePartnerPreviewToggle({
  visible,
}: {
  visible: boolean;
}) {
  const [persona, setPersona] = useState<PreviewPersona>("");

  useEffect(() => {
    if (!visible) return;
    setPersona(getPreviewPersona());
    const onChange = () => setPersona(getPreviewPersona());
    window.addEventListener("ced-preview-persona", onChange);
    window.addEventListener("popstate", onChange);
    return () => {
      window.removeEventListener("ced-preview-persona", onChange);
      window.removeEventListener("popstate", onChange);
    };
  }, [visible]);

  const exit = useCallback(() => {
    setPreviewPersona("");
    setPersona("");
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete("previewAs");
      window.history.replaceState({}, "", url.toString());
    } catch {
      /* ignore */
    }
  }, []);

  const enter = useCallback(() => {
    setPreviewPersona("cierre");
    setPersona("cierre");
  }, []);

  if (!visible) return null;

  const active = persona === "cierre" || isCierrePartnerPreview();

  if (active) {
    return (
      <button
        type="button"
        onClick={exit}
        className="rounded border-2 border-amber-400 bg-amber-500/20 px-2.5 py-1.5 font-[family-name:var(--font-orbitron)] text-[9px] font-bold tracking-wider text-amber-100 hover:bg-amber-500/30 sm:px-3 sm:text-[10px]"
        title="Salir del modo socio Cierre $20"
      >
        SALIR PRUEBA PM
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={enter}
      className="rounded border-2 border-emerald-400/80 bg-emerald-500/15 px-2.5 py-1.5 font-[family-name:var(--font-orbitron)] text-[9px] font-bold tracking-wider text-emerald-100 hover:bg-emerald-500/25 sm:px-3 sm:text-[10px]"
      title="Ver CED como socio nuevo del plan Cierre $20 (PM International / FitLine)"
    >
      PROBAR SOCIO PM
    </button>
  );
}

/** Banner de estado cuando el modo prueba está activo. */
export function CierrePartnerPreviewBanner({
  visible,
}: {
  visible?: boolean;
}) {
  const [active, setActive] = useState(false);

  useEffect(() => {
    const sync = () => setActive(isCierrePartnerPreview());
    sync();
    window.addEventListener("ced-preview-persona", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("ced-preview-persona", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  if (visible === false || !active) return null;

  return (
    <div className="mx-auto mb-2 flex max-w-3xl flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-100">
      <span>
        Modo prueba activo: experiencia de <strong>socio nuevo</strong> plan{" "}
        <strong>Cierre $20</strong> (FitLine / PM International).
      </span>
      <button
        type="button"
        onClick={() => {
          setPreviewPersona("");
          setActive(false);
          try {
            const url = new URL(window.location.href);
            url.searchParams.delete("previewAs");
            window.history.replaceState({}, "", url.toString());
          } catch {
            /* ignore */
          }
        }}
        className="shrink-0 rounded border border-amber-400/50 px-2 py-1 text-[11px] font-medium text-amber-50 hover:bg-amber-500/20"
      >
        Salir
      </button>
    </div>
  );
}
