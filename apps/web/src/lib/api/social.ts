import { parseApiJson } from "@/lib/api/http";
import { proxyFetch } from "@/lib/api/ced-proxy";

export type PublishImageInput = {
  imageUrl?: string;
  imageData?: string;
};

export async function publishFacebook(
  message: string,
  image?: PublishImageInput,
): Promise<{ ok: true; spoken: string } | { ok: false; error: string }> {
  try {
    const res = await proxyFetch("meta/publish/facebook", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        image_url: image?.imageUrl ?? null,
        imageData: image?.imageData ?? null,
      }),
    });
    const data = await parseApiJson<{ spoken?: string; detail?: string }>(res);
    if (!res.ok) {
      return {
        ok: false,
        error: data.detail ?? "No se pude publicar en Facebook.",
      };
    }
    return { ok: true, spoken: data.spoken ?? "Publicado." };
  } catch {
    return { ok: false, error: "Error de red al publicar en Facebook." };
  }
}

export async function publishInstagram(
  caption: string,
  image: PublishImageInput,
): Promise<{ ok: true; spoken: string } | { ok: false; error: string }> {
  try {
    const res = await proxyFetch("meta/publish/instagram", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        caption,
        image_url: image.imageUrl ?? null,
        imageData: image.imageData ?? null,
      }),
    });
    const data = await parseApiJson<{ spoken?: string; detail?: string }>(res);
    if (!res.ok) {
      return {
        ok: false,
        error: data.detail ?? "No se pude publicar en Instagram.",
      };
    }
    return { ok: true, spoken: data.spoken ?? "Publicado." };
  } catch {
    return { ok: false, error: "Error de red al publicar en Instagram." };
  }
}

export async function uploadPublishImage(
  imageData: string,
): Promise<{ ok: true; url: string } | { ok: false; error: string }> {
  try {
    const res = await proxyFetch("media/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: imageData }),
    });
    const data = await parseApiJson<{ ok?: boolean; url?: string; error?: string }>(
      res,
    );
    if (!res.ok || !data.ok || !data.url) {
      return { ok: false, error: data.error ?? "No se pudo subir la imagen." };
    }
    return { ok: true, url: data.url };
  } catch {
    return { ok: false, error: "Error de red al subir imagen." };
  }
}
