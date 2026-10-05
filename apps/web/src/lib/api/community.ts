import { proxyFetch } from "@/lib/api/ced-proxy";
import { parseApiJson } from "@/lib/api/http";

export type CommunityRoomId = "prompts" | "guiones" | "copies" | "ayuda";

export type CommunityReply = {
  id: string;
  body: string;
  token: string;
  display_name: string;
  mine: boolean;
  created_at: string;
};

export type CommunityPost = {
  id: string;
  room: CommunityRoomId;
  title: string;
  body: string;
  token: string;
  display_name: string;
  mine: boolean;
  created_at: string;
  reactions: Record<string, number>;
  replies: CommunityReply[];
  reply_count: number;
};

export type CommunityMeta = {
  ok: boolean;
  rooms: { id: CommunityRoomId; label: string; hint: string }[];
  tokens: { id: string; src: string }[];
  rules: string[];
  me: { user_id: string; token: string; display_name: string };
  persistence: "db" | "memory";
};

async function read<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await parseApiJson<{
      detail?: string | { msg?: string };
      error?: string;
    }>(res).catch(() => ({ detail: undefined, error: undefined }));
    const detail = typeof err.detail === "string" ? err.detail : err.detail?.msg;
    throw new Error(detail || err.error || "La sala no respondió.");
  }
  return parseApiJson<T>(res);
}

export async function fetchCommunityMeta(): Promise<CommunityMeta> {
  return read(await proxyFetch("community/meta"));
}

export async function saveCommunityToken(token: string) {
  return read<{ ok: boolean; me: CommunityMeta["me"] }>(
    await proxyFetch("community/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }),
  );
}

export async function fetchCommunityPosts(room?: string): Promise<CommunityPost[]> {
  const q = room ? `?room=${encodeURIComponent(room)}` : "";
  const data = await read<{ posts: CommunityPost[] }>(
    await proxyFetch(`community/posts${q}`),
  );
  return data.posts || [];
}

export async function createCommunityPost(body: {
  room: string;
  title: string;
  body: string;
  token: string;
}) {
  return read<{ ok: boolean; post: CommunityPost }>(
    await proxyFetch("community/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function replyCommunityPost(
  postId: string,
  body: string,
  token: string,
) {
  return read<{ ok: boolean; reply: CommunityReply }>(
    await proxyFetch(`community/posts/${postId}/replies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body, token }),
    }),
  );
}

export async function reactCommunityPost(postId: string, token: string) {
  return read<{ ok: boolean; reactions: Record<string, number> }>(
    await proxyFetch(`community/posts/${postId}/react`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }),
  );
}

export async function reportCommunityPost(postId: string) {
  return read<{ ok: boolean }>(
    await proxyFetch(`community/posts/${postId}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "report" }),
    }),
  );
}
