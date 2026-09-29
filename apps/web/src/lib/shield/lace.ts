/**
 * Lace / Midnight DApp connector via window.midnight.
 * No instala midnight.js en el bundle de CED (el HUD de voz no lo carga).
 *
 * Firma (signData) = atestación real de la wallet.
 * submitTransaction exige un tx Compact ya probado — no se inventa un txid.
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

export type LaceLiveSnapshot = {
  address: string;
  networkId: string;
  indexerUri?: string;
  substrateNodeUri?: string;
  dustBalance?: string;
  canSignData: boolean;
  canSubmitTx: boolean;
  canProve: boolean;
};

export type LaceSignature = {
  data: string;
  signature: string;
  verifyingKey: string;
};

type ConnectedApi = {
  getUnshieldedAddress?: () => Promise<string | { unshieldedAddress?: string }>;
  getConnectionStatus?: () => Promise<{ status?: string; networkId?: string }>;
  getUsedAddresses?: () => Promise<string[]>;
  getConfiguration?: () => Promise<{
    indexerUri?: string;
    indexerWsUri?: string;
    substrateNodeUri?: string;
    networkId?: string;
    proverServerUri?: string;
  }>;
  getDustBalance?: () => Promise<{ cap?: bigint | string | number; balance?: bigint | string | number }>;
  hintUsage?: (methods: string[]) => Promise<void>;
  signData?: (...args: unknown[]) => Promise<unknown>;
  signMessage?: (...args: unknown[]) => Promise<unknown>;
  experimental?: { signData?: (...args: unknown[]) => Promise<unknown> };
  submitTransaction?: (tx: string) => Promise<void>;
  getProvingProvider?: (keys: unknown) => Promise<unknown>;
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

type LaceSession = {
  api: ConnectedApi;
  meta: LaceOk;
};

let _session: LaceSession | null = null;

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

export function getLaceSession(): LaceSession | null {
  return _session;
}

export function clearLaceSession(): void {
  _session = null;
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

function stringifyQty(value: bigint | string | number | undefined): string | undefined {
  if (value === undefined || value === null) return undefined;
  try {
    return String(value);
  } catch {
    return undefined;
  }
}

function isStaleLaceChannel(detail: string): boolean {
  return /midnight-wallet|se ha desactivado|no se puede utilizar|disconnected|invalidated|message port/i.test(
    detail,
  );
}

const STALE_CHANNEL_HINT =
  "Lace se durmió (canal midnight-wallet). Abra el icono de Lace Midnight Preview, recargue esta página y pulse Conectar otra vez.";

async function wait(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
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

async function connectOnce(network: string): Promise<LaceResult> {
  const picked = pickProvider();
  if (!picked) {
    return { ok: false, reason: "no_extension" };
  }

  const { name, provider } = picked;
  let api: ConnectedApi = provider;
  if (typeof provider.connect === "function") {
    api = await provider.connect(network);
  } else if (typeof provider.enable === "function") {
    const enabled = await provider.enable();
    if (enabled && typeof enabled === "object") {
      api = enabled as ConnectedApi;
    }
  }

  const live = api ?? provider;
  const { address, networkId } = await readAddress(live);
  if (!address) {
    return {
      ok: false,
      reason: "error",
      detail: "Lace no devolvió una dirección. Abra la extensión y pruebe de nuevo.",
    };
  }
  const meta: LaceOk = {
    ok: true,
    address,
    networkId,
    source: name,
    apiVersion: provider.apiVersion,
  };
  _session = { api: live, meta };
  return meta;
}

export async function connectLace(network: string = LACE_NETWORK): Promise<LaceResult> {
  _session = null;
  let last: LaceResult = { ok: false, reason: "no_extension" };

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      last = await connectOnce(network);
      if (last.ok) return last;
      if (last.reason === "no_extension") return last;
      break;
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      if (/reject|denied|cancel/i.test(detail)) {
        _session = null;
        return { ok: false, reason: "user_rejected", detail };
      }
      if (isStaleLaceChannel(detail) && attempt === 0) {
        await wait(400);
        continue;
      }
      _session = null;
      return {
        ok: false,
        reason: "error",
        detail: isStaleLaceChannel(detail) ? STALE_CHANNEL_HINT : detail,
      };
    }
  }

  _session = last.ok ? _session : null;
  if (!last.ok && last.reason === "error" && last.detail && isStaleLaceChannel(last.detail)) {
    return { ok: false, reason: "error", detail: STALE_CHANNEL_HINT };
  }
  return last;
}

export async function readLaceLive(): Promise<LaceLiveSnapshot | null> {
  if (!_session) return null;
  const { api, meta } = _session;
  try {
    const liveAddr = await readAddress(api);
    if (liveAddr.address) {
      _session.meta = {
        ...meta,
        address: liveAddr.address,
        networkId: liveAddr.networkId || meta.networkId,
      };
    }
  } catch {
    /* keep last known address */
  }
  const snap: LaceLiveSnapshot = {
    address: _session.meta.address,
    networkId: _session.meta.networkId,
    canSignData: typeof api.signData === "function",
    canSubmitTx: typeof api.submitTransaction === "function",
    canProve: typeof api.getProvingProvider === "function",
  };
  if (typeof api.getConfiguration === "function") {
    try {
      const cfg = await api.getConfiguration();
      snap.indexerUri = cfg.indexerUri;
      snap.substrateNodeUri = cfg.substrateNodeUri;
      if (cfg.networkId) snap.networkId = String(cfg.networkId);
    } catch {
      /* older preview */
    }
  }
  if (typeof api.getDustBalance === "function") {
    try {
      const dust = await api.getDustBalance();
      snap.dustBalance = stringifyQty(dust.balance);
    } catch {
      /* optional */
    }
  }
  return snap;
}

function errText(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === "string" && err.trim()) return err;
  try {
    return JSON.stringify(err) || String(err);
  } catch {
    return String(err);
  }
}

function isNotImplemented(detail: string): boolean {
  return /no implementado|not implemented|not yet implemented/i.test(detail);
}

function asLaceSignature(value: unknown): LaceSignature | null {
  if (typeof value === "string" && value.trim()) {
    return { data: "", signature: value.trim(), verifyingKey: "" };
  }
  if (!value || typeof value !== "object") return null;
  const rec = value as Record<string, unknown>;
  const signature =
    rec.signature ?? rec.cose_sign1 ?? rec.signatureHex ?? rec.sig;
  const verifyingKey =
    rec.verifyingKey ?? rec.publicKey ?? rec.key ?? rec.cose_key ?? "";
  const data = rec.data ?? rec.signedData ?? rec.message ?? "";
  if (typeof signature !== "string" || !signature.trim()) return null;
  return {
    data: typeof data === "string" ? data : "",
    signature: signature.trim(),
    verifyingKey: typeof verifyingKey === "string" ? verifyingKey : "",
  };
}

async function invokeSign(
  fn: (...args: unknown[]) => Promise<unknown>,
  args: unknown[],
): Promise<{ ok: true; signature: LaceSignature } | { ok: false; detail: string }> {
  try {
    const raw = await fn(...args);
    const signature = asLaceSignature(raw);
    if (!signature) {
      return { ok: false, detail: "Lace no devolvió firma." };
    }
    return { ok: true, signature };
  } catch (err) {
    return { ok: false, detail: errText(err) };
  }
}

export async function signCommitmentHex(
  messageHex: string,
  messageText?: string,
): Promise<
  | { ok: true; signature: LaceSignature }
  | { ok: false; reason: "no_session" | "no_signData" | "user_rejected" | "error"; detail?: string }
> {
  if (!_session) {
    return { ok: false, reason: "no_session", detail: "Conecte Lace primero." };
  }
  const { api } = _session;

  if (typeof api.hintUsage === "function") {
    try {
      await api.hintUsage(["signData", "getUnshieldedAddress", "getConfiguration"]);
    } catch {
      /* Lace Preview 2.39 stub: hintUsage throws "Método no implementado". */
    }
  }

  const attempts: Array<{
    fn?: (...args: unknown[]) => Promise<unknown>;
    args: unknown[];
  }> = [
    {
      fn: api.signData,
      args: [messageHex, { encoding: "hex", keyType: "unshielded" }],
    },
    {
      fn: api.signData,
      args: [messageText || messageHex, { encoding: "text", keyType: "unshielded" }],
    },
    { fn: api.signData, args: [messageHex] },
    { fn: api.experimental?.signData, args: [messageHex] },
    { fn: api.signMessage, args: [messageText || messageHex] },
  ];

  let lastDetail = "";
  let sawNotImplemented = false;
  for (const attempt of attempts) {
    if (typeof attempt.fn !== "function") continue;
    const result = await invokeSign(attempt.fn, attempt.args);
    if (result.ok) return result;
    lastDetail = result.detail;
    if (/reject|denied|cancel/i.test(result.detail)) {
      return { ok: false, reason: "user_rejected", detail: result.detail };
    }
    if (isNotImplemented(result.detail)) {
      sawNotImplemented = true;
      continue;
    }
    return { ok: false, reason: "error", detail: result.detail };
  }

  if (sawNotImplemented || typeof api.signData !== "function") {
    return {
      ok: false,
      reason: "no_signData",
      detail:
        "Lace no implementa signData (Preview 2.39 y la Lace principal). El hash y la wallet ya son reales. No se finge firma.",
    };
  }
  return {
    ok: false,
    reason: "error",
    detail: lastDetail || "Lace no firmó el sello.",
  };
}
