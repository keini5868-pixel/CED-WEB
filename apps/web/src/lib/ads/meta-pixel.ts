/** Pixel de Meta para la campaña de lanzamiento CED. Sin ID, no hace nada. */

export const META_PIXEL_STORAGE = {
  expectRegistration: "ced_pixel_expect_registration",
  didRegistration: "ced_pixel_did_complete_registration",
  didStartTrial: "ced_pixel_did_start_trial",
} as const;

type Fbq = ((...args: unknown[]) => void) & {
  callMethod?: (...args: unknown[]) => void;
  queue?: unknown[];
  loaded?: boolean;
  version?: string;
  push?: Fbq;
};

declare global {
  interface Window {
    fbq?: Fbq;
    _fbq?: Fbq;
  }
}

export function readMetaPixelId(raw: string | undefined | null): string {
  const id = (raw || "").trim();
  return /^\d{6,20}$/.test(id) ? id : "";
}

export function metaPixelId(): string {
  return readMetaPixelId(process.env.NEXT_PUBLIC_META_PIXEL_ID);
}

function storageGet(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

export function markExpectedRegistration(): void {
  storageSet(META_PIXEL_STORAGE.expectRegistration, "1");
}

export function trackMeta(event: string, params?: Record<string, string | number>): void {
  if (typeof window === "undefined") return;
  if (!metaPixelId()) return;
  const fbq = window.fbq;
  if (typeof fbq !== "function") return;
  if (params && Object.keys(params).length > 0) {
    fbq("track", event, params);
    return;
  }
  fbq("track", event);
}

export function trackPageView(): void {
  trackMeta("PageView");
}

export function trackCompleteRegistration(): void {
  if (storageGet(META_PIXEL_STORAGE.didRegistration) === "1") return;
  trackMeta("CompleteRegistration", { content_name: "ced_signup" });
  storageSet(META_PIXEL_STORAGE.didRegistration, "1");
}

export function consumeExpectedRegistration(): void {
  if (storageGet(META_PIXEL_STORAGE.expectRegistration) !== "1") return;
  try {
    window.sessionStorage.removeItem(META_PIXEL_STORAGE.expectRegistration);
  } catch {
    /* ignore */
  }
  trackCompleteRegistration();
}

export function trackStartTrial(): void {
  if (storageGet(META_PIXEL_STORAGE.didStartTrial) === "1") return;
  trackMeta("StartTrial", { content_name: "ced_voice", value: 0, currency: "USD" });
  storageSet(META_PIXEL_STORAGE.didStartTrial, "1");
}

export function trackPurchase(opts: {
  value?: number;
  currency?: string;
  planId?: string;
  eventId?: string;
}): void {
  const value = Number(opts.value);
  const safeValue = Number.isFinite(value) && value > 0 ? Math.round(value * 100) / 100 : 0;
  const eventId = (opts.eventId || "").trim();
  const dedupeKey = eventId ? `ced_pixel_purchase_${eventId}` : "";
  if (dedupeKey && storageGet(dedupeKey) === "1") return;
  const params: Record<string, string | number> = {
    value: safeValue,
    currency: opts.currency || "USD",
    content_name: opts.planId ? `ced_plan_${opts.planId}` : "ced_purchase",
  };
  trackMeta("Purchase", params);
  if (dedupeKey) storageSet(dedupeKey, "1");
}
