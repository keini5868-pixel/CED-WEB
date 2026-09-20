/**
 * Lace / Midnight DApp connector via window.midnight.
 * No instala midnight.js en el bundle de CED (el HUD de voz no lo carga).
 */

export const LACE_NETWORK = "preprod";

export type LaceOk = {
  ok: true;
  address: string;
  networkId: string;
  source: string;
  apiVersion?: string;
};

export type LaceErr = {
  ok: false;
  reason: "no_extension" | "user_rejected" | "error";
  detail?: string;
};

export type LaceResult = LaceOk | LaceErr;

type ConnectedApi = {
  getUnshieldedAddress?: () => Promise<string | { unshieldedAddress?: string }>;
  getConnectionStatus?: () => Promise<{ status?: string; networkId?: string }>;
  getUsedAddresses?: () => Promise<string[]>;
  state?: () => Promise<{
    address?: string;
    coinPublicKey?: string;
    networkId?: string;
  }>;
};

type MidnightProvider = ConnectedApi & {
  apiVersion?: string;
  name?: string;
  connect?: (network: string) => Promise<ConnectedApi>;
  enable?: () => Promise<ConnectedApi | boolean | void>;
  isEnabled?: () => Promise<boolean>;
};

function midnightRoot(): Record<string, MidnightProvider> | null {
  if (typeof window === "undefined") return null;
  const root = (window as Window & { midnight?: Record<string, MidnightProvider> })
    .midnight;
  if (!root || typeof root !== "object") return null;
  return root;
}

export function laceInstalled(): boolean {
  return Boolean(pickProvider());
}

function pickProvider(): { name: string; provider: MidnightProvider } | null {
  const root = midnightRoot();
  if (!root) return null;
  const entries = Object.entries(root).filter(
    ([, provider]) => provider && typeof provider === "object",
  );
  if (!entries.length) return null;
  const lace = entries.find(([name]) => /lace|mnlace/i.test(name));
  const picked = lace ?? entries[0];
  if (!picked) return null;
  const [name, provider] = picked;
  return { name, provider };
}

function asAddress(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (value && typeof value === "object") {
    const rec = value as Record<string, unknown>;
    for (const key of ["unshieldedAddress", "address", "coinPublicKey"]) {
      const item = rec[key];
      if (typeof item === "string" && item.trim()) return item.trim();
    }
  }
  return "";
}

async function readAddress(api: ConnectedApi): Promise<{ address: string; networkId: string }> {
  let address = "";
  let networkId = LACE_NETWORK;

  if (typeof api.getUnshieldedAddress === "function") {
    try {
      address = asAddress(await api.getUnshieldedAddress());
    } catch {
      /* v1 wallets may not expose this */
    }
  }
  if (!address && typeof api.state === "function") {
    try {
      const state = await api.state();
      address = asAddress(state);
      if (state?.networkId) networkId = String(state.networkId);
    } catch {
      /* ignore */
    }
  }
  if (!address && typeof api.getUsedAddresses === "function") {
    try {
      const used = await api.getUsedAddresses();
      if (Array.isArray(used) && used[0]) address = String(used[0]).trim();
    } catch {
      /* ignore */
    }
  }
  if (typeof api.getConnectionStatus === "function") {
    try {
      const status = await api.getConnectionStatus();
      if (status?.networkId) networkId = String(status.networkId);
    } catch {
      /* ignore */
    }
  }
  return { address, networkId };
}

export async function connectLace(network: string = LACE_NETWORK): Promise<LaceResult> {
  const picked = pickProvider();
  if (!picked) {
    return { ok: false, reason: "no_extension" };
  }

  const { name, provider } = picked;
  try {
    let api: ConnectedApi = provider;
    if (typeof provider.connect === "function") {
      api = await provider.connect(network);
    } else if (typeof provider.enable === "function") {
      const enabled = await provider.enable();
      if (enabled && typeof enabled === "object") {
        api = enabled as ConnectedApi;
      }
    }

    const { address, networkId } = await readAddress(api ?? provider);
    if (!address) {
      return {
        ok: false,
        reason: "error",
        detail: "Lace no devolvió una dirección. Abra la extensión y pruebe de nuevo.",
      };
    }
    return {
      ok: true,
      address,
      networkId,
      source: name,
      apiVersion: provider.apiVersion,
    };
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    if (/reject|denied|cancel/i.test(detail)) {
      return { ok: false, reason: "user_rejected", detail };
    }
    return { ok: false, reason: "error", detail };
  }
}
