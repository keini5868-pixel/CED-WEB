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
  const durationSec = Math.max(0.1, Number(body.duration_sec) || 30);
  const filename = body.file.name || "source.mp4";

  // 1) URL firmada Shotstack (JSON pequeño vía BFF — el MP4 NO pasa por Next)
  const ingestRes = await proxyFetch("video-edit-pilot/ingest-upload", {
    method: "POST",
    headers: await _authedJsonHeaders(),
    body: JSON.stringify({ filename }),
  });
  const ingest = (await ingestRes.json().catch(() => ({}))) as {
    ok?: boolean;
    source_id?: string;
    upload_url?: string;
    detail?: unknown;
    error?: string;
  };
  if (!ingestRes.ok || !ingest.upload_url || !ingest.source_id) {
    return {
      ok: false,
      message:
        formatApiDetail(ingest.detail) ||
        ingest.error ||
        "No se pudo obtener URL de subida a Shotstack.",
    };
  }

  // 2) PUT directo del browser → S3 de Shotstack (sin BFF)
  try {
    const putRes = await fetch(ingest.upload_url, {
      method: "PUT",
      body: body.file,
      // Sin Content-Type forzado: la firma S3 suele no incluirlo
    });
    if (!putRes.ok) {
      const hint = await putRes.text().catch(() => "");
      return {
        ok: false,
        message: `Fallo al subir el video a Shotstack (HTTP ${putRes.status}). ${hint.slice(0, 180)}`,
      };
    }
  } catch (err) {
    return {
      ok: false,
      message:
        err instanceof Error
          ? `No se pudo subir el video: ${err.message}`
          : "No se pudo subir el video a Shotstack (CORS/red).",
    };
  }

  // 3) Arrancar render async con source_id (JSON vía BFF)
  const renderRes = await proxyFetch("video-edit-pilot/render-from-source", {
    method: "POST",
    headers: await _authedJsonHeaders(),
    body: JSON.stringify({
      source_id: ingest.source_id,
      duration_sec: durationSec,
      script: body.script || "",
      auto_transcribe: Boolean(body.auto_transcribe),
    }),
  });
  const data = (await renderRes.json().catch(() => ({}))) as VideoEditRenderResult & {
    detail?: unknown;
  };
  const started = parseRenderResponse(renderRes, data);
  if (started.job_id && started.status === "rendering") {
    savePendingVideoEditJob(started.job_id);
  }
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

const PENDING_JOB_KEY = "ced.videoEdit.pendingJobId";

export function savePendingVideoEditJob(jobId: string | null): void {
  try {
    if (!jobId) {
      sessionStorage.removeItem(PENDING_JOB_KEY);
      return;
    }
    sessionStorage.setItem(PENDING_JOB_KEY, jobId);
  } catch {
    /* private mode */
  }
}

export function loadPendingVideoEditJob(): string | null {
  try {
    return sessionStorage.getItem(PENDING_JOB_KEY);
  } catch {
    return null;
  }
}

/** Poll hasta done/failed. Por defecto ~12 min (edits con varios clips tardan más). */
export async function pollVideoEditJob(
  jobId: string,
  initial?: VideoEditRenderResult,
  opts?: { timeoutMs?: number; intervalMs?: number; onTick?: (r: VideoEditRenderResult) => void },
): Promise<VideoEditRenderResult> {
  const timeoutMs = opts?.timeoutMs ?? 720_000;
  const intervalMs = opts?.intervalMs ?? 3000;
  const deadline = Date.now() + timeoutMs;
  let last: VideoEditRenderResult = initial || {
    ok: true,
    job_id: jobId,
    status: "rendering",
    message: "Render en curso…",
  };
  savePendingVideoEditJob(jobId);
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs));
    last = await fetchVideoEditJob(jobId);
    opts?.onTick?.(last);
    const status = String(last.status || "");
    if (status === "done" || status === "failed" || status === "dry_run") {
      savePendingVideoEditJob(null);
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
    code: "still_rendering",
    job_id: jobId,
    status: last.status || "rendering",
    message:
      "El render sigue en curso (puede tardar varios minutos con varios cortes). "
      + "Pulse «Seguir esperando» — no genere de nuevo o se cobrará otra vez.",
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
