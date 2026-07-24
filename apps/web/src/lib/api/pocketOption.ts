import { cedApiPath } from "@/lib/api/ced-proxy";

export type PocketOptionTrade = {
  id: string;
  ts: string;
  strategy: "bos" | "alternating";
  direction: "call" | "put";
  asset: string;
  amount: number;
  expiry_seconds: number;
  level: number;
  reason: string;
  result: string;
  profit?: number | null;
  error?: string | null;
};

export type PocketOptionStatus = {
  enabled: boolean;
  ssid_configured: boolean;
  running: boolean;
  connected: boolean;
  is_demo: boolean | null;
  balance: number | null;
  asset: string;
  next_slot_at: string | null;
  last_error: string | null;
  circuit_open: boolean;
  strategy_bos_enabled: boolean;
  strategy_alt_enabled: boolean;
  interval_seconds: number;
  amount?: number;
  expiry_seconds?: number;
  trades: PocketOptionTrade[];
};

export async function fetchPocketOptionStatus(): Promise<PocketOptionStatus | null> {
  const res = await fetch(cedApiPath("admin/pocket-option/status"), {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as PocketOptionStatus;
}
