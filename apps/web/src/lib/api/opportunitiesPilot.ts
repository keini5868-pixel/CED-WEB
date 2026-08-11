import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

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
  embed?: {
    type?: string;
    video_id?: string;
    url?: string;
  } | null;
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
    source?: string;
    has_own?: boolean;
  };
  action_plan?: FitlineActionPlan | null;
  sections?: OpportunitySection[];
  sources?: {
    curated?: Array<{ title?: string; url?: string }>;
    search?: Array<{ title?: string; url?: string; snippet?: string }>;
  };
  data_gaps?: string[];
  pilot?: boolean;
  production?: boolean;
};

export type FitlineActionPlan = {
  id?: string;
  title?: string;
  status?: string;
  content?: {
    goals?: string[];
    steps?: string[];
    notes?: string;
    horizon?: string;
    franchise_focus?: string;
  };
  updated_at?: string;
};

export type FitlineSponsorInfo = {
  ok?: boolean;
  url?: string;
  configured?: boolean;
  source?: string;
  has_own?: boolean;
  has_default?: boolean;
  cta_label?: string;
  saved_url?: string;
};

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

export async function fetchOpportunitiesPilotStatus(): Promise<{
  enabled: boolean;
  sponsor_url_configured?: boolean;
  sponsor?: FitlineSponsorInfo;
  has_action_plan?: boolean;
} | null> {
  try {
    const res = await proxyFetchAuthed("opportunities-pilot/status", {
      headers: jsonHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as {
      enabled: boolean;
      sponsor_url_configured?: boolean;
      sponsor?: FitlineSponsorInfo;
      has_action_plan?: boolean;
    };
  } catch {
    return null;
  }
}

export async function fetchFitlineSponsor(): Promise<FitlineSponsorInfo> {
  const res = await proxyFetchAuthed("opportunities-pilot/sponsor", {
    headers: jsonHeaders(),
  });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return (await res.json()) as FitlineSponsorInfo;
}

export async function saveFitlineSponsor(url: string): Promise<FitlineSponsorInfo> {
  const res = await proxyFetchAuthed("opportunities-pilot/sponsor", {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Error ${res.status}`);
  }
  return (await res.json()) as FitlineSponsorInfo;
}

export async function fetchFitlineActionPlan(): Promise<{
  plan: FitlineActionPlan | null;
}> {
  const res = await proxyFetchAuthed("opportunities-pilot/action-plan", {
    headers: jsonHeaders(),
  });
  if (!res.ok) throw new Error(`Error ${res.status}`);
  const data = (await res.json()) as { plan?: FitlineActionPlan | null };
  return { plan: data.plan ?? null };
}

export async function saveFitlineActionPlan(body: {
  title?: string;
  content?: FitlineActionPlan["content"];
}): Promise<{ plan: FitlineActionPlan }> {
  const res = await proxyFetchAuthed("opportunities-pilot/action-plan", {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Error ${res.status}`);
  }
  return (await res.json()) as { plan: FitlineActionPlan };
}

export async function fetchOpportunitiesCatalog(): Promise<OpportunitySummary[]> {
  const res = await proxyFetchAuthed("opportunities-pilot/catalog", {
    headers: jsonHeaders(),
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
    { headers: jsonHeaders() },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Error ${res.status}`);
  }
  return (await res.json()) as OpportunityDetail;
}

export const OPPORTUNITIES_WELCOME =
  "Oportunidades de negocio disponibles en CED. Por ahora: PM International / FitLine. Contenido base curado más búsqueda con fuentes; sin inventar cifras de ingreso.";
