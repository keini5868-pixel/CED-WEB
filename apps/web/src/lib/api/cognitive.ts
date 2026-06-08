import { proxyFetch } from "@/lib/api/ced-proxy";

export type CognitiveRouteResult = {
  intent: string;
  channel: string;
  confidence: number;
  domain_id?: string | null;
  domain_label?: string | null;
  speakable?: string | null;
  needs_advanced_confirm?: boolean;
  source?: string | null;
};

export async function routeCognitiveMessage(
  text: string,
  channel: "voice" | "text" = "text",
  options?: { confirmPending?: boolean },
): Promise<CognitiveRouteResult | null> {
  try {
    const res = await proxyFetch("cognitive/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        channel,
        confirm_pending: Boolean(options?.confirmPending),
        execute: true,
      }),
    });
    if (!res.ok) return null;
    return (await res.json()) as CognitiveRouteResult;
  } catch {
    return null;
  }
}

export async function fetchCognitiveDomains(): Promise<
  { id: string; label: string; time_sensitive: boolean }[]
> {
  try {
    const res = await proxyFetch("cognitive/domains");
    if (!res.ok) return [];
    const data = (await res.json()) as { domains?: { id: string; label: string; time_sensitive: boolean }[] };
    return data.domains ?? [];
  } catch {
    return [];
  }
}
