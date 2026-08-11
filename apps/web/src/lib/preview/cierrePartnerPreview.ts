/**
 * Modo prueba: admin ve CED como socio nuevo plan Cierre ($20 PM/FitLine).
 * Activar: ?previewAs=cierre  |  Desactivar: ?previewAs=off
 */

import { clearEphemeralTokenCache } from "@/lib/voice/ephemeralTokenCache";

const STORAGE_KEY = "ced_preview_as";
export const PREVIEW_CIERRE = "cierre";
export const PREVIEW_HEADER = "X-CED-Preview-As";

export type PreviewPersona = typeof PREVIEW_CIERRE | "";

function readStorage(): PreviewPersona {
  if (typeof window === "undefined") return "";
  try {
    const v = (localStorage.getItem(STORAGE_KEY) || "").trim().toLowerCase();
    return v === PREVIEW_CIERRE ? PREVIEW_CIERRE : "";
  } catch {
    return "";
  }
}

export function getPreviewPersona(): PreviewPersona {
  if (typeof window === "undefined") return "";
  try {
    const params = new URLSearchParams(window.location.search);
    const q = (params.get("previewAs") || "").trim().toLowerCase();
    if (q === "off" || q === "false" || q === "0") {
      setPreviewPersona("");
      return "";
    }
    if (q === PREVIEW_CIERRE || q === "1" || q === "true" || q === "new") {
      setPreviewPersona(PREVIEW_CIERRE);
      return PREVIEW_CIERRE;
    }
  } catch {
    /* ignore */
  }
  return readStorage();
}

export function setPreviewPersona(value: PreviewPersona): void {
  if (typeof window === "undefined") return;
  try {
    if (value === PREVIEW_CIERRE) {
      localStorage.setItem(STORAGE_KEY, PREVIEW_CIERRE);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    try {
      clearEphemeralTokenCache();
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new CustomEvent("ced-preview-persona", { detail: value }));
  } catch {
    /* ignore */
  }
}

export function isCierrePartnerPreview(): boolean {
  return getPreviewPersona() === PREVIEW_CIERRE;
}

export function previewPersonaHeaders(): Record<string, string> {
  if (!isCierrePartnerPreview()) return {};
  return { [PREVIEW_HEADER]: PREVIEW_CIERRE };
}

export function cierrePreviewVoiceRoute(): {
  planId: string;
  voiceStack: string;
  voiceTransport: string;
} {
  /** Preview PM usa Retell Jarvis (voz económica OpenAI retirada). */
  return {
    planId: "cierre",
    voiceStack: "retell",
    voiceTransport: "retell",
  };
}
