export type CedReminder = {
  id: string;
  text: string;
  date: string;
  time: string;
  createdAt: string;
};

const KEY = "ced:hud-reminders";

export function listReminders(): CedReminder[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as CedReminder[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveReminder(input: {
  text: string;
  date: string;
  time: string;
}): CedReminder {
  const item: CedReminder = {
    id: crypto.randomUUID(),
    text: input.text.trim(),
    date: input.date,
    time: input.time,
    createdAt: new Date().toISOString(),
  };
  const next = [...listReminders(), item].slice(-20);
  localStorage.setItem(KEY, JSON.stringify(next));
  return item;
}

export function upcomingReminders(): CedReminder[] {
  const now = Date.now();
  const sorted = listReminders().sort(
    (a, b) =>
      new Date(`${a.date}T${a.time || "09:00"}`).getTime() -
      new Date(`${b.date}T${b.time || "09:00"}`).getTime(),
  );
  const upcoming = sorted.filter((r) => {
    const when = new Date(`${r.date}T${r.time || "09:00"}`).getTime();
    return !Number.isNaN(when) && when >= now - 86_400_000;
  });
  if (upcoming.length) return upcoming;
  return sorted.slice(-8).reverse();
}

export async function loadRemindersMerged(): Promise<CedReminder[]> {
  const local = listReminders();
  try {
    const { fetchHudReminders } = await import("@/lib/api/hudActions");
    const remote = await fetchHudReminders();
    const byKey = new Map<string, CedReminder>();
    for (const item of remote.reminders) {
      const key = `${item.date}|${item.time}|${item.text}`;
      byKey.set(key, {
        id: item.id,
        text: item.text,
        date: item.date,
        time: item.time || "09:00",
        createdAt: new Date().toISOString(),
      });
    }
    for (const item of local) {
      const key = `${item.date}|${item.time}|${item.text}`;
      if (!byKey.has(key)) byKey.set(key, item);
    }
    const merged = [...byKey.values()].sort(
      (a, b) =>
        new Date(`${a.date}T${a.time || "09:00"}`).getTime() -
        new Date(`${b.date}T${b.time || "09:00"}`).getTime(),
    );
    if (typeof window !== "undefined" && merged.length) {
      localStorage.setItem(KEY, JSON.stringify(merged.slice(-20)));
    }
    const now = Date.now();
    const upcoming = merged.filter((r) => {
      const when = new Date(`${r.date}T${r.time || "09:00"}`).getTime();
      return !Number.isNaN(when) && when >= now - 86_400_000;
    });
    return upcoming.length ? upcoming : merged.slice(-8);
  } catch {
    return upcomingReminders();
  }
}

export async function saveReminderWithSync(input: {
  text: string;
  date: string;
  time: string;
}): Promise<{ item: CedReminder; synced: boolean; error?: string }> {
  const item = saveReminder(input);
  try {
    const { createHudReminder } = await import("@/lib/api/hudActions");
    const result = await createHudReminder({
      text: input.text,
      date: input.date,
      time: input.time,
    });
    return { item, synced: result.ok, error: result.error };
  } catch {
    return { item, synced: false, error: "No se pudo sincronizar con el servidor." };
  }
}
