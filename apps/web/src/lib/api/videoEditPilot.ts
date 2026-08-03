import { authHeaders } from "@/lib/api/auth";
import { proxyFetch } from "@/lib/api/ced-proxy";
import {
  VIDEO_EDIT_PILOT_HEADER,
  VIDEO_EDIT_PILOT_HEADER_VALUE,
} from "@/lib/pilot/videoEditModule";

function pilotJsonHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    "Content-Type": "application/json",
    [VIDEO_EDIT_PILOT_HEADER]: VIDEO_EDIT_PILOT_HEADER_VALUE,
    ...(extra || {}),
  };
}

export type VideoEditPack = {
  amount_paid_usd: number;
  tokens: number;
  seconds_equivalent: number;
  base_videos_30s: number;
};

export type VideoEditBalance = {
  ok: boolean;
  balance_tokens: number;
  balance_seconds: number;
  renders_today: number;
  soft_cap_per_day: number;
  soft_cap_remaining: number;
  packs: VideoEditPack[];
};

export type VideoEditQuote = {
  ok: boolean;
  duration_sec: number;
  billable_seconds: number;
  tokens: number;
  price_usd: number;
  margin_percent?: number;
};

export type VideoEditRenderResult = {
  ok: boolean;
  job_id?: string;
  status?: string;
  tokens_charged?: number;
  balance_tokens?: number;
  timeline?: Record<string, unknown>;
  message?: string;
  error?: string;
  code?: string;
  result_url?: string;
  soft_cap_remaining?: number;
  quote?: VideoEditQuote;
  detail?: unknown;
};

function parseRenderResponse(
  res: Response,
  data: VideoEditRenderResult & { detail?: VideoEditRenderResult | string },
): VideoEditRenderResult {
  if (!res.ok) {
    const detail = data.detail;
    if (detail && typeof detail === "object") {
      const err = detail as VideoEditRenderResult;
      return {
        ok: false,
        job_id: err.job_id,
        status: err.status,
        tokens_charged: err.tokens_charged,
        balance_tokens: err.balance_tokens,
        timeline: err.timeline,
        result_url: err.result_url,
        message: err.message || err.error || "No se pudo procesar el video.",
        error: err.error,
        code: err.code,
        soft_cap_remaining: err.soft_cap_remaining,
        quote: err.quote,
        detail: err.detail,
      };
    }
    return {
      ok: false,
      message: typeof detail === "string" ? detail : "No se pudo procesar el video.",
    };
  }
  return data;
}

export async function fetchVideoEditStatus(): Promise<{
  enabled: boolean;
  mode?: string;
  economy?: Record<string, unknown>;
  providers?: Record<string, unknown>;
} | null> {
  try {
    const res = await proxyFetch("video-edit-pilot/status", {
      headers: await _authedJsonHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as { enabled: boolean };
  } catch {
    return null;
  }
}

export async function fetchVideoEditBalance(): Promise<VideoEditBalance | null> {
  try {
    const res = await proxyFetch("video-edit-pilot/balance", {
      headers: await _authedJsonHeaders(),
    });
    if (!res.ok) return null;
    return (await res.json()) as VideoEditBalance;
  } catch {
    return null;
  }
}

export async function quoteVideoEdit(
  durationSec: number,
): Promise<VideoEditQuote | null> {
  try {
    const res = await proxyFetch("video-edit-pilot/quote", {
      method: "POST",
      headers: await _authedJsonHeaders(),
      body: JSON.stringify({ duration_sec: durationSec }),
    });
    if (!res.ok) return null;
    return (await res.json()) as VideoEditQuote;
  } catch {
    return null;
  }
}

async function _authedJsonHeaders(): Promise<Record<string, string>> {
  const auth = await authHeaders(true).catch(() => ({} as Record<string, string>));
  return {
    ...(auth as Record<string, string>),
    ...pilotJsonHeaders(),
  };
}

export async function renderVideoEdit(body: {
  duration_sec: number;
  script: string;
  file?: File | null;
  auto_transcribe?: boolean;
}): Promise<VideoEditRenderResult> {
  if (!body.file || body.file.size <= 0) {
    return {
      ok: false,
      code: "missing_video",
      message: "Seleccione de nuevo el archivo de video antes de generar.",
    };
  }
  const form = new FormData();
  // Video primero: si hay límites de body, no perder el archivo al final
  form.append("video", body.file, body.file.name || "source.mp4");
  form.append("duration_sec", String(body.duration_sec));
  form.append("script", body.script || "");
  form.append("auto_transcribe", body.auto_transcribe ? "true" : "false");

  const auth = await authHeaders(false).catch(() => ({} as Record<string, string>));
  const headers: Record<string, string> = {
    ...(auth as Record<string, string>),
    [VIDEO_EDIT_PILOT_HEADER]: VIDEO_EDIT_PILOT_HEADER_VALUE,
  };
  // Crítico: nunca forzar Content-Type con FormData (rompe el boundary)
  delete headers["Content-Type"];
  delete headers["content-type"];

  const res = await proxyFetch("video-edit-pilot/render", {
    method: "POST",
    headers,
    body: form,
  });
  const data = (await res.json().catch(() => ({}))) as VideoEditRenderResult & {
    detail?: VideoEditRenderResult | string;
  };
  return parseRenderResponse(res, data);
}

export async function checkoutVideoEditPack(
  amountUsd: number,
): Promise<{ url?: string; error?: string }> {
  const res = await proxyFetch("video-edit-pilot/checkout", {
    method: "POST",
    headers: await _authedJsonHeaders(),
    body: JSON.stringify({ amount_usd: amountUsd }),
  });
  const data = (await res.json().catch(() => ({}))) as {
    url?: string;
    detail?: string;
  };
  if (!res.ok) {
    return { error: data.detail || "No se pudo iniciar el pago." };
  }
  return { url: data.url };
}
