import { proxyFetchAuthed } from "@/lib/api/ced-proxy";

export type ManyChatRole = "closer" | "qualifier" | "support" | "custom";
export type ManyChatTone = "cercano" | "formal" | "directo";
export type ManyChatCtaWhen = "ready" | "always" | "never";

export type ManyChatMessage = {
  id: string;
  subscriber_id?: string;
  direction?: string;
  body?: string;
  created_at?: string;
};

export type ManyChatStatus = {
  ok: boolean;
  allowed: boolean;
  access_reason?: string;
  webhook_url: string;
  webhook_secret: string;
  enabled: boolean;
  role: ManyChatRole;
  tone: ManyChatTone;
  mission: string;
  ask_lines: string;
  objections: string;
  never_say: string;
  cta_when: ManyChatCtaWhen;
  cta_url: string;
  cta_label: string;
  presets: Record<string, { label: string; mission: string }>;
  setup: string[];
  messages: ManyChatMessage[];
  error?: string;
};

export type ManyChatBehavior = {
  enabled?: boolean;
  role: ManyChatRole;
  tone: ManyChatTone;
  mission: string;
  ask_lines: string;
  objections: string;
  never_say: string;
  cta_when: ManyChatCtaWhen;
  cta_url: string;
  cta_label: string;
};

function formatApiError(data: unknown, status: number): string {
  const rec =
    data && typeof data === "object" ? (data as Record<string, unknown>) : {};
  const detail = rec.detail ?? rec.error ?? rec.message;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const row = item as Record<string, unknown>;
        return String(row.msg || row.message || "").trim();
      }
      return "";
    });
    const joined = parts.filter(Boolean).join(" ");
    if (joined) return joined;
  }
  if (detail && typeof detail === "object") {
    const row = detail as Record<string, unknown>;
    const msg = row.msg || row.message || row.detail;
    if (typeof msg === "string" && msg.trim()) return msg.trim();
  }
  return status === 401
    ? "Tu sesión expiró. Recarga e inicia sesión."
    : "No se pudo guardar. Recarga e inténtalo otra vez.";
}

async function readJson<T>(res: Response): Promise<T & { error?: string }> {
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    return { ...data, error: formatApiError(data, res.status) };
  }
  return data;
}

export async function fetchManyChatStatus(): Promise<ManyChatStatus> {
  const res = await proxyFetchAuthed("manychat/status");
  return readJson<ManyChatStatus>(res);
}

export async function saveManyChatBehavior(
  body: ManyChatBehavior,
): Promise<ManyChatStatus> {
  const payload: Record<string, unknown> = {
    role: body.role,
    tone: body.tone,
    mission: body.mission,
    ask_lines: body.ask_lines,
    objections: body.objections,
    never_say: body.never_say,
    cta_when: body.cta_when,
    cta_url: body.cta_url,
    cta_label: body.cta_label,
  };
  if (typeof body.enabled === "boolean") {
    payload.enabled = body.enabled;
  }
  const res = await proxyFetchAuthed("manychat/behavior", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson<ManyChatStatus>(res);
}

export async function rotateManyChatSecret(): Promise<ManyChatStatus> {
  const res = await proxyFetchAuthed("manychat/secret/rotate", { method: "POST" });
  return readJson<ManyChatStatus>(res);
}
