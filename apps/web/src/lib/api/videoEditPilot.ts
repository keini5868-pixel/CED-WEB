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

function formatApiDetail(detail: unknown): string {
  if (detail == null) return "No se pudo procesar el video.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const row = item as { msg?: string; message?: string; loc?: unknown[] };
          const where = Array.isArray(row.loc) ? row.loc.join(".") : "";
          const msg = row.msg || row.message || JSON.stringify(item);
          return where ? `${where}: ${msg}` : msg;
        }
        return String(item);
      })
      .join(" · ");
  }
  if (typeof detail === "object") {
    const err = detail as VideoEditRenderResult & { detail?: unknown };
    const msg = err.message || err.error;
    if (msg) return String(msg);
    if (err.detail != null) return formatApiDetail(err.detail);
    try {
      return JSON.stringify(detail).slice(0, 400);
    } catch {
      return "No se pudo procesar el video.";
    }
  }
  return String(detail);
}

function parseRenderResponse(
  res: Response,
  data: VideoEditRenderResult & { detail?: unknown },
): VideoEditRenderResult {
  if (!res.ok) {
    const detail = data.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const err = detail as VideoEditRenderResult;
      return {
        ok: false,
        job_id: err.job_id,
        status: err.status,
        tokens_charged: err.tokens_charged,
        balance_tokens: err.balance_tokens,
        timeline: err.timeline,
        result_url: err.result_url,
        message: formatApiDetail(detail),
        error: err.error,
        code: err.code,
        soft_cap_remaining: err.soft_cap_remaining,
        quote: err.quote,
        detail: err.detail,
      };
    }
    return {
      ok: false,
      message: `HTTP ${res.status}: ${formatApiDetail(detail)}`,
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
  const started = parseRenderResponse(res, data);
  if (!started.ok || started.status !== "rendering" || !started.job_id) {
    return started;
  }
  return pollVideoEditJob(started.job_id, started);
}

export async function fetchVideoEditJob(
  jobId: string,
): Promise<VideoEditRenderResult> {
  const res = await proxyFetch(`video-edit-pilot/jobs/${encodeURIComponent(jobId)}`, {
    headers: await _authedJsonHeaders(),
  });
  const data = (await res.json().catch(() => ({}))) as VideoEditRenderResult & {
    detail?: unknown;
  };
  if (!res.ok) {
    return {
      ok: false,
      message: formatApiDetail(data.detail) || `HTTP ${res.status}`,
    };
  }
  return data;
}

async function pollVideoEditJob(
  jobId: string,
  initial: VideoEditRenderResult,
): Promise<VideoEditRenderResult> {
  const deadline = Date.now() + 280_000;
  let last = initial;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2500));
    last = await fetchVideoEditJob(jobId);
    const status = String(last.status || "");
    if (status === "done" || status === "failed" || status === "dry_run") {
      if (status === "failed") {
        return {
          ...last,
          ok: false,
          message:
            last.message ||
            last.error ||
            "Render falló. Tokens reembolsados si correspondía.",
        };
      }
      return { ...last, ok: true };
    }
  }
  return {
    ok: false,
    job_id: jobId,
    status: last.status || "rendering",
    message:
      "El render sigue en curso pero el tiempo de espera del cliente se agotó. "
      + "Vuelva a abrir el módulo en unos minutos o reintente.",
  };
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
    return { error: typeof data.detail === "string" ? data.detail : "No se pudo iniciar el pago." };
  }
  return { url: data.url };
}
