import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

import type { UserGender } from "@/lib/voice/addressPreferenceIntent";
import { cedResolveHonorific } from "@/lib/voice/live/ced-brief-messages";

export type UserAddressContext = {
  displayName: string;
  firstName: string;
  honorific: string;
  gender: UserGender | null;
  preferredAddress: string | null;
  greetingPhraseJarvis: string;
  greetingPhraseStandard: string;
};

function normalizeAddressPayload(data: Record<string, unknown>): UserAddressContext {
  const gender = (data.gender as UserGender | null) ?? null;
  const raw: UserAddressContext = {
    displayName: String(data.displayName || ""),
    firstName: String(data.firstName || ""),
    honorific: String(data.honorific || ""),
    gender,
    preferredAddress: data.preferredAddress ? String(data.preferredAddress) : null,
    greetingPhraseJarvis: String(data.greetingPhraseJarvis || ""),
    greetingPhraseStandard: String(data.greetingPhraseStandard || ""),
  };
  const honorific = cedResolveHonorific(raw);
  return { ...raw, honorific };
}

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

export async function fetchUserAddress(): Promise<UserAddressContext | null> {
  try {
    const res = await authFetch("/v1/profile/address");
    const data = (await res.json()) as Record<string, unknown>;
    if (!res.ok || data.ok === false) return null;
    return normalizeAddressPayload(data);
  } catch {
    return null;
  }
}

export async function updateUserAddress(prefs: {
  preferredAddress?: string;
  gender?: UserGender | null;
}): Promise<UserAddressContext | null> {
  try {
    const body: Record<string, string | null> = {};
    if (prefs.preferredAddress !== undefined) {
      const trimmed = prefs.preferredAddress.trim();
      const valid =
        trimmed &&
        trimmed.length >= 3 &&
        !/^(si|sí|se|me|te|lo|la|que|ke|ok|va)$/i.test(trimmed.replace(/\./g, ""));
      body.preferredAddress = valid ? trimmed : null;
    }
    if (prefs.gender !== undefined) {
      body.gender = prefs.gender;
    }
    const res = await authFetch("/v1/profile/address", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    const data = (await res.json()) as Record<string, unknown>;
    if (!res.ok || data.ok === false) return null;
    return normalizeAddressPayload(data);
  } catch {
    return null;
  }
}
