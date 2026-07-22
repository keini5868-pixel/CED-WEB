import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import {
  VIABILITY_PILOT_HEADER,
  VIABILITY_PILOT_HEADER_VALUE,
} from "@/lib/pilot/viabilityModule";

export type ViabilityCompetitor = {
  name: string;
  note: string;
  competition_basis?: string;
  source_url?: string;
  source_title?: string;
  attribution?: string;
};

export type ViabilityReport = {
  ok: boolean;
  offering_summary?: string;
  region?: string;
  likelihood?: {
    range: string;
    label: string;
    rationale: string;
    attribution?: string;
  };
  competitors?: ViabilityCompetitor[];
  pricing?: {
    findings: Array<{
      text: string;
      context?: string;
      source_url?: string;
      source_title?: string;
    }>;
  };
  trends?: Array<{ text: string; source_url?: string; source_title?: string }>;
  improvements?: Array<{ idea: string; attribution?: string }>;
  data_gaps?: string[];
  search_meta?: {
    sources?: number;
    result_rows?: number;
    errors?: Array<{ error?: string }>;
    rate_limited?: boolean;
    fallback_used?: boolean;
    missing_key?: boolean;
  };
  report_markdown?: string;
  research_markdown?: string;
  advice_markdown?: string;
  spoken?: string;
  sources?: Array<{
    purpose?: string;
    query?: string;
    title?: string;
    url?: string;
    snippet?: string;
  }>;
  queries?: Array<{ purpose: string; query: string }>;
  pilot?: boolean;
};

function pilotHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    [VIABILITY_PILOT_HEADER]: VIABILITY_PILOT_HEADER_VALUE,
  };
}

export async function fetchViabilityPilotStatus(): Promise<{
  enabled: boolean;
  tavily?: boolean;
  google?: boolean;
} | null> {
  try {
    const res = await proxyFetchAuthed("viability-pilot/status", {
      headers: pilotHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as { enabled: boolean };
  } catch {
    return null;
  }
}

export async function analyzeViability(params: {
  description?: string;
  imageBase64?: string;
  region?: string;
}): Promise<ViabilityReport> {
  const res = await proxyFetchAuthed("viability-pilot/analyze", {
    method: "POST",
    headers: pilotHeaders(),
    body: JSON.stringify({
      description: params.description || null,
      image_base64: params.imageBase64 || null,
      region: params.region || null,
      require_intent_phrasing: false,
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Error ${res.status}`);
  }
  return (await res.json()) as ViabilityReport;
}

export const VIABILITY_WELCOME =
  "Módulo piloto de viabilidad. Describa un producto o servicio, o suba un flyer/foto, y generaré un informe con hechos de búsqueda separados del consejo estratégico. No inventaré competidores ni precios.";
