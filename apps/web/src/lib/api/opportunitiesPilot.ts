import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import {
  OPPORTUNITIES_PILOT_HEADER,
  OPPORTUNITIES_PILOT_HEADER_VALUE,
} from "@/lib/pilot/opportunitiesModule";

export type OpportunitySummary = {
  id: string;
  title: string;
  tagline: string;
  status: string;
};

export type OpportunitySearchNote = {
  text: string;
  source_title?: string;
  source_url?: string;
  attribution?: string;
};

export type OpportunitySection = {
  id: string;
  title: string;
  body: string;
  attribution?: string;
  search_updates?: OpportunitySearchNote[];
  honest_risks?: boolean;
};

export type OpportunityDetail = {
  ok: boolean;
  id: string;
  title: string;
  tagline?: string;
  curated_as_of?: string;
  sponsorship?: {
    url?: string;
    cta_label?: string;
    configured?: boolean;
  };
  sections?: OpportunitySection[];
  sources?: {
    curated?: Array<{ title?: string; url?: string }>;
    search?: Array<{ title?: string; url?: string; snippet?: string }>;
  };
  data_gaps?: string[];
  pilot?: boolean;
};

function pilotHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    [OPPORTUNITIES_PILOT_HEADER]: OPPORTUNITIES_PILOT_HEADER_VALUE,
  };
}

export async function fetchOpportunitiesPilotStatus(): Promise<{
  enabled: boolean;
  sponsor_url_configured?: boolean;
} | null> {
  try {
    const res = await proxyFetchAuthed("opportunities-pilot/status", {
      headers: pilotHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as {
      enabled: boolean;
      sponsor_url_configured?: boolean;
    };
  } catch {
    return null;
  }
}

export async function fetchOpportunitiesCatalog(): Promise<OpportunitySummary[]> {
  const res = await proxyFetchAuthed("opportunities-pilot/catalog", {
    headers: pilotHeaders(),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Error ${res.status}`);
  }
  const data = (await res.json()) as { opportunities?: OpportunitySummary[] };
  return data.opportunities || [];
}

export async function fetchOpportunityDetail(
  opportunityId: string,
): Promise<OpportunityDetail> {
  const res = await proxyFetchAuthed(
    `opportunities-pilot/opportunities/${encodeURIComponent(opportunityId)}`,
    { headers: pilotHeaders() },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Error ${res.status}`);
  }
  return (await res.json()) as OpportunityDetail;
}

export const OPPORTUNITIES_WELCOME =
  "Módulo piloto de oportunidades. Por ahora: PM International / FitLine. Contenido base curado más búsqueda con fuentes; sin inventar cifras de ingreso.";
