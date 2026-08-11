"use client";

import { useCallback, useEffect, useState } from "react";

import { useIsSuperAdminClient } from "@/hooks/useIsSuperAdminClient";
import {
  getPreviewPersona,
  isCierrePartnerPreview,
  setPreviewPersona,
  type PreviewPersona,
} from "@/lib/preview/cierrePartnerPreview";

/** Banner + sync URL/localStorage para probar CED como socio Cierre $20. */
export function CierrePartnerPreviewBanner() {
  const { isAdmin, loaded } = useIsSuperAdminClient();
  const [persona, setPersona] = useState<PreviewPersona>("");

  useEffect(() => {
    setPersona(getPreviewPersona());
    const onChange = () => setPersona(getPreviewPersona());
    window.addEventListener("ced-preview-persona", onChange);
    window.addEventListener("popstate", onChange);
    return () => {
      window.removeEventListener("ced-preview-persona", onChange);
      window.removeEventListener("popstate", onChange);
    };
  }, []);

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

  if (!loaded || !isAdmin) return null;

  if (persona === "cierre" || isCierrePartnerPreview()) {
    return (
      <div className="mx-auto mb-2 flex max-w-3xl flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-100">
        <span>
          Modo prueba: estás viendo CED como <strong>socio nuevo</strong> del plan{" "}
          <strong>Cierre $20</strong> (FitLine / PM International) — sin privilegios de
          admin en voz/guía.
        </span>
        <button
          type="button"
          onClick={exit}
          className="shrink-0 rounded border border-amber-400/50 px-2 py-1 text-[11px] font-medium text-amber-50 hover:bg-amber-500/20"
        >
          Salir del modo prueba
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto mb-2 flex max-w-3xl flex-wrap items-center justify-end gap-2 px-1">
      <button
        type="button"
        onClick={enter}
        className="rounded border border-white/15 bg-black/30 px-2.5 py-1 text-[11px] text-slate-300 hover:border-cyan-500/40 hover:text-cyan-200"
        title="Simular plan Cierre $20 como usuario nuevo"
      >
        Probar como socio Cierre $20
      </button>
    </div>
  );
}
