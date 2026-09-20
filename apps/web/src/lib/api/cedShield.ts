import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type ShieldStatus = {
  enabled: boolean;
  module: string;
  on_chain: string;
  never_on_chain: string[];
  voice_untouched: boolean;
  compact_contract?: string;
  compact_circuit?: string;
  lace_network?: string;
  demo_path?: string;
  kill_switch?: string;
};

export async function fetchShieldStatus(): Promise<ShieldStatus | null> {
  try {
    const res = await proxyFetchAuthed("v1/shield/status", { cache: "no-store" });
    if (!res.ok) return null;
    return await parseApiJson<ShieldStatus>(res);
  } catch {
    return null;
  }
}
