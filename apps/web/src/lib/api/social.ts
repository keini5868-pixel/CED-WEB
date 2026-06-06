import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    throw new Error("Inicia sesión");
  }
  return fetch(`${apiUrl()}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string>),
    },
  });
}

export async function publishFacebook(
  message: string,
  imageUrl?: string,
): Promise<{ ok: true; spoken: string } | { ok: false; error: string }> {
  try {
    const res = await authFetch("/v1/meta/publish/facebook", {
      method: "POST",
      body: JSON.stringify({ message, image_url: imageUrl ?? null }),
    });
    const data = (await res.json()) as { spoken?: string; detail?: string };
    if (!res.ok) {
      return { ok: false, error: data.detail ?? "No se pudo publicar en Facebook." };
    }
    return { ok: true, spoken: data.spoken ?? "Señor, publicación enviada a Facebook." };
  } catch {
    return { ok: false, error: "Error de red al publicar en Facebook." };
  }
}

export async function publishInstagram(
  caption: string,
  imageUrl: string,
): Promise<{ ok: true; spoken: string } | { ok: false; error: string }> {
  try {
    const res = await authFetch("/v1/meta/publish/instagram", {
      method: "POST",
      body: JSON.stringify({ caption, image_url: imageUrl }),
    });
    const data = (await res.json()) as { spoken?: string; detail?: string };
    if (!res.ok) {
      return { ok: false, error: data.detail ?? "No se pudo publicar en Instagram." };
    }
    return { ok: true, spoken: data.spoken ?? "Señor, publicación enviada a Instagram." };
  } catch {
    return { ok: false, error: "Error de red al publicar en Instagram." };
  }
}
