import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

const CALENDAR_EVENT_TIMEOUT_MS = 90_000;
const RETRYABLE_STATUSES = new Set([502, 503, 504]);

function normalizeEventDate(raw: string): string {
  const trimmed = raw.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return trimmed;
  }
  const slash = trimmed.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (slash) {
    const day = slash[1] ?? "01";
    const month = slash[2] ?? "01";
    const year = slash[3] ?? "2026";
    return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
  }
  return trimmed;
}

function normalizeEventTime(raw: string): string {
  const trimmed = raw.trim() || "09:00";
  if (/^\d{2}:\d{2}$/.test(trimmed)) return trimmed;
  const parts = trimmed.match(/^(\d{1,2}):(\d{2})$/);
  if (parts) {
    const h = parts[1] ?? "9";
    const m = parts[2] ?? "00";
    return `${h.padStart(2, "0")}:${m}`;
  }
  return "09:00";
}

async function postHudJson(
  path: string,
  payload: Record<string, unknown>,
  timeoutMs: number,
): Promise<{ ok: boolean; error?: string }> {
  const delays = [0, 1500, 3500];
  let lastError = "No se pudo completar la operación.";

  for (let attempt = 0; attempt < delays.length; attempt += 1) {
    if (delays[attempt]) {
      await new Promise((resolve) => setTimeout(resolve, delays[attempt]));
    }
    try {
      const res = await proxyFetchAuthed(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(timeoutMs),
      });
      const data = await parseApiJson<{ ok?: boolean; detail?: string; error?: string }>(
        res,
      );
      if (res.ok) {
        return { ok: true };
      }
      lastError = data.detail || data.error || lastError;
      if (!RETRYABLE_STATUSES.has(res.status) || attempt === delays.length - 1) {
        return { ok: false, error: lastError };
      }
    } catch (err) {
      if (err instanceof Error) {
        if (err.name === "TimeoutError" || err.name === "AbortError") {
          lastError = "La API tardó demasiado. Reintenta en unos segundos.";
        } else {
          lastError = err.message;
        }
      }
      if (attempt === delays.length - 1) {
        return { ok: false, error: lastError };
      }
    }
  }

  return { ok: false, error: lastError };
}

export async function createHudReminder(payload: {
  text: string;
  date: string;
  time: string;
}): Promise<{ ok: boolean; error?: string }> {
  return postHudJson(
    "hud/reminders",
    {
      text: payload.text,
      date: normalizeEventDate(payload.date),
      time: normalizeEventTime(payload.time),
    },
    45_000,
  );
}

export async function fetchHudReminders(): Promise<{
  reminders: Array<{ id: string; text: string; date: string; time: string }>;
  error?: string;
}> {
  try {
    const res = await proxyFetchAuthed("hud/reminders", { method: "GET" });
    if (!res.ok) {
      const body = await res.text();
      return { reminders: [], error: body || `HTTP ${res.status}` };
    }
    const data = (await res.json()) as {
      reminders?: Array<{ id: string; text: string; date: string; time: string }>;
    };
    return { reminders: data.reminders ?? [] };
  } catch (e) {
    return {
      reminders: [],
      error: e instanceof Error ? e.message : "No se pudieron cargar recordatorios.",
    };
  }
}

export async function createHudCalendarEvent(payload: {
  title: string;
  date: string;
  time: string;
  reminder_minutes?: number;
}): Promise<{ ok: boolean; error?: string }> {
  return postHudJson(
    "hud/calendar/event",
    {
      title: payload.title.trim(),
      date: normalizeEventDate(payload.date),
      time: normalizeEventTime(payload.time),
      reminder_minutes: payload.reminder_minutes,
    },
    CALENDAR_EVENT_TIMEOUT_MS,
  );
}

export async function sendHudGmail(payload: {
  to: string;
  subject: string;
  body: string;
}): Promise<{ ok: boolean; error?: string }> {
  return postHudJson("hud/gmail/send", payload, 60_000);
}
