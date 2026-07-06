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
  return listReminders()
    .filter((r) => {
      const when = new Date(`${r.date}T${r.time || "09:00"}`).getTime();
      return !Number.isNaN(when) && when >= now - 86_400_000;
    })
    .sort(
      (a, b) =>
        new Date(`${a.date}T${a.time}`).getTime() -
        new Date(`${b.date}T${b.time}`).getTime(),
    );
}
