import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export async function createHudCalendarEvent(payload: {
  title: string;
  date: string;
  time: string;
  reminder_minutes?: number;
}): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await proxyFetchAuthed("hud/calendar/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseApiJson<{ ok?: boolean; detail?: string; error?: string }>(res);
    if (!res.ok) {
      return { ok: false, error: data.detail || data.error || "No se pudo crear el evento." };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "Error de red al crear evento." };
  }
}

export async function sendHudGmail(payload: {
  to: string;
  subject: string;
  body: string;
}): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await proxyFetchAuthed("hud/gmail/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseApiJson<{ ok?: boolean; detail?: string; error?: string }>(res);
    if (!res.ok) {
      return { ok: false, error: data.detail || data.error || "No se pudo enviar el email." };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "Error de red al enviar email." };
  }
}
