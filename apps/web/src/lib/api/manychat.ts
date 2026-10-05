import { proxyFetch } from "@/lib/api/ced-proxy";

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

async function readJson<T>(res: Response): Promise<T & { error?: string }> {
  const data = (await res.json().catch(() => ({}))) as T & {
    error?: string;
    detail?: string;
  };
  if (!res.ok) {
    const detail = data.detail || data.error || `Error ${res.status}`;
    return { ...data, error: String(detail) };
  }
  return data;
}

export async function fetchManyChatStatus(): Promise<ManyChatStatus> {
  const res = await proxyFetch("manychat/status");
  return readJson<ManyChatStatus>(res);
}

export async function saveManyChatBehavior(
  body: ManyChatBehavior,
): Promise<ManyChatStatus> {
  const res = await proxyFetch("manychat/behavior", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<ManyChatStatus>(res);
}

export async function rotateManyChatSecret(): Promise<ManyChatStatus> {
  const res = await proxyFetch("manychat/secret/rotate", { method: "POST" });
  return readJson<ManyChatStatus>(res);
}
