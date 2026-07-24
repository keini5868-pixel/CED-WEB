import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

export type TrendsFinding = {
  text: string;
  source_title?: string;
  source_url?: string;
  attribution?: string;
};

export type TrendsReport = {
  ok: boolean;
  description?: string;
  region?: string;
  profile?: {
    anchor?: string;
    industry_label?: string;
    category?: string;
    product_kind?: string;
    named_entities?: string[];
  };
  trending_now?: TrendsFinding[];
  consumer_needs?: TrendsFinding[];
  outlook_6m?: {
    attribution: "search" | "model_reasoning";
    findings: TrendsFinding[];
    model_note?: string | null;
  };
  opportunities?: Array<{
    idea: string;
    attribution?: string;
    source_url?: string;
  }>;
  data_gaps?: string[];
  search_meta?: {
    sources?: number;
    missing_key?: boolean;
    rate_limited?: boolean;
    errors?: Array<{ error?: string }>;
  };
  report_markdown?: string;
  spoken?: string;
  queries?: Array<{ purpose: string; query: string }>;
  pilot?: boolean;
  production?: boolean;
};

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export async function fetchTrendsPilotStatus(): Promise<{
  enabled: boolean;
  tavily?: boolean;
} | null> {
  try {
    const res = await proxyFetchAuthed("trends-pilot/status", {
      headers: jsonHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as { enabled: boolean };
  } catch {
    return null;
  }
}

export async function analyzeTrends(params: {
  description: string;
  region?: string;
}): Promise<TrendsReport> {
  const res = await proxyFetchAuthed("trends-pilot/analyze", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      description: params.description,
      region: params.region || null,
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Error ${res.status}`);
  }
  return (await res.json()) as TrendsReport;
}

export const TRENDS_WELCOME =
  "Módulo de tendencias. Describa su rubro o industria y generaré un informe con hallazgos de búsqueda separados del razonamiento. Nombres propios anclan la búsqueda; no invento porcentajes sin fuente.";
