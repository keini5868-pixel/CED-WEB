import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type TrashScope = "conversation" | "image" | "pdf" | "finance";

export type TrashItem = {
  id: string;
  scope: TrashScope;
  title: string;
  deleted_at?: string | null;
  purge_after?: string | null;
  preview?: string | null;
};

async function trashJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await proxyFetchAuthed(path, init);
  const data = await parseApiJson<T & { detail?: unknown }>(res);
  if (!res.ok) {
    throw new Error("No se pudo actualizar la papelera.");
  }
  return data;
}

export async function fetchTrash(scope?: TrashScope): Promise<TrashItem[]> {
  const qs = scope ? `?scope=${encodeURIComponent(scope)}` : "";
  const data = await trashJson<{ items?: TrashItem[] }>(`trash${qs}`);
  return data.items ?? [];
}

export async function sendToTrash(scope: TrashScope, ids: string[]): Promise<number> {
  if (ids.length === 0) return 0;
  const data = await trashJson<{ count?: number }>("trash", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, ids }),
  });
  return data.count ?? ids.length;
}

export async function restoreFromTrash(scope: TrashScope, ids: string[]): Promise<number> {
  if (ids.length === 0) return 0;
  const data = await trashJson<{ count?: number }>("trash/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, ids }),
  });
  return data.count ?? ids.length;
}

export async function purgeFromTrash(scope: TrashScope, ids: string[]): Promise<number> {
  if (ids.length === 0) return 0;
  const data = await trashJson<{ count?: number }>("trash/purge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scope, ids }),
  });
  return data.count ?? ids.length;
}
