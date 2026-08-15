import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

export type ReferralGuestStatus = "active" | "idle" | "unused";

export type ReferralSignals = {
  voice: { used: boolean; pm_context: boolean; minutes_14d: number };
  chat_sales: { used: boolean; pm_questions: number };
  finance: { used: boolean };
  opps: { used: boolean; viewed_ficha: boolean; own_sponsor: boolean };
};

export type ReferralGuest = {
  id: string;
  display_name: string;
  joined_at: string | null;
  status: ReferralGuestStatus;
  last_relevant_at: string | null;
  signals: ReferralSignals;
};

export type MyTeamResponse = {
  ok: boolean;
  referral_code: string;
  invite_url: string;
  counts: {
    total: number;
    active: number;
    idle: number;
    unused: number;
  };
  guests: ReferralGuest[];
  criteria: {
    voice: string;
    chat_sales: string;
    finance: string;
    opps: string;
  };
};

export async function fetchMyTeam(): Promise<MyTeamResponse> {
  const res = await proxyFetchAuthed("dashboard/mi-equipo", { method: "GET" });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || "No se pudo cargar tu equipo.");
  }
  return (await res.json()) as MyTeamResponse;
}
