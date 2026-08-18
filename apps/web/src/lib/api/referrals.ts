import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

export type ReferralGuestStatus = "active" | "idle" | "unused" | "pending";

export type ReferralSignals = {
  voice: { used: boolean; pm_context: boolean; minutes_14d: number };
  chat_sales: { used: boolean; pm_questions: number };
  finance: { used: boolean };
  opps: { used: boolean; viewed_ficha: boolean; own_sponsor: boolean };
};

export type ReferralGuest = {
  id: string;
  display_name: string;
  full_name: string;
  email: string;
  ced_id: string;
  joined_at: string | null;
  status: ReferralGuestStatus;
  last_relevant_at: string | null;
  signals: ReferralSignals;
};

export type MyTeamMe = {
  email: string;
  full_name: string;
  referral_code: string;
  pm_partner_id?: string;
  needs_onboarding: boolean;
};

export type MyTeamResponse = {
  ok: boolean;
  referral_code: string;
  invite_url: string;
  me?: MyTeamMe;
  counts: {
    total: number;
    active: number;
    idle: number;
    unused: number;
    pending?: number;
  };
  guests: ReferralGuest[];
  criteria: {
    voice: string;
    chat_sales: string;
    finance: string;
    opps: string;
  };
};

async function readError(res: Response, fallback: string): Promise<string> {
  const detail = await res.text().catch(() => "");
  try {
    const parsed = JSON.parse(detail) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    /* texto plano */
  }
  return detail || fallback;
}

export async function fetchMyTeam(): Promise<MyTeamResponse> {
  const res = await proxyFetchAuthed("dashboard/mi-equipo", { method: "GET" });
  if (!res.ok) {
    throw new Error(await readError(res, "No se pudo cargar tu equipo."));
  }
  return (await res.json()) as MyTeamResponse;
}

export async function savePmProfile(input: {
  full_name: string;
  pm_partner_id?: string;
  sponsor_ced_id?: string;
}): Promise<MyTeamResponse> {
  const res = await proxyFetchAuthed("referrals/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      full_name: input.full_name,
      pm_partner_id: input.pm_partner_id || "",
      sponsor_ced_id: input.sponsor_ced_id || "",
    }),
  });
  if (!res.ok) {
    throw new Error(await readError(res, "No se pudo guardar tu ficha."));
  }
  return (await res.json()) as MyTeamResponse;
}

export async function addPmPartner(input: {
  full_name: string;
  email: string;
  pm_partner_id: string;
}): Promise<MyTeamResponse> {
  const res = await proxyFetchAuthed("referrals/partners", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      full_name: input.full_name,
      email: input.email,
      pm_partner_id: input.pm_partner_id,
    }),
  });
  if (!res.ok) {
    throw new Error(await readError(res, "No se pudo añadir el socio."));
  }
  return (await res.json()) as MyTeamResponse;
}
