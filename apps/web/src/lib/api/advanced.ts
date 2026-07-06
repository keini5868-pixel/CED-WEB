import { proxyFetchAuthed } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type AdvancedChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
};

export type AdvancedChatStatus = {
  configured: boolean;
  model: string | null;
};

export async function fetchAdvancedChatStatus(): Promise<AdvancedChatStatus | null> {
  try {
    const res = await proxyFetchAuthed("advanced/status");
    if (!res.ok) return null;
    return (await res.json()) as AdvancedChatStatus;
  } catch {
    return null;
  }
}

export async function sendAdvancedChatMessage(
  message: string,
  history: AdvancedChatMessage[],
): Promise<{ response: string; model: string }> {
  const res = await proxyFetchAuthed("advanced/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history: history.map((m) => ({ role: m.role, content: m.content })),
    }),
  });
  const data = await parseApiJson<{
    response?: string;
    model?: string;
    detail?: string;
  }>(res);
  if (!res.ok) {
    throw new Error(data.detail || "No se pudo obtener respuesta de Claude.");
  }
  return {
    response: data.response ?? "",
    model: data.model ?? "claude-opus-4-6",
  };
}
