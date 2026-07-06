"use client";

import { fetchGoogleCalendarOAuthUrl, fetchGoogleGmailOAuthUrl } from "@/lib/api/google";

export type LifeActionDetail = {
  prompt: string;
  activateVoice?: boolean;
};

export const CED_LIFE_ACTION_EVENT = "ced-life-action";

export function dispatchLifeVoicePrompt(prompt: string) {
  window.dispatchEvent(
    new CustomEvent(CED_LIFE_ACTION_EVENT, {
      detail: { prompt, activateVoice: true } satisfies LifeActionDetail,
    }),
  );
}

export async function connectGoogleCalendarFromLife() {
  const { url, error } = await fetchGoogleCalendarOAuthUrl();
  if (!url) {
    window.alert(error || "No se pudo iniciar OAuth Calendar.");
    return;
  }
  window.location.href = url;
}

export async function connectGoogleGmailFromLife() {
  const { url, error } = await fetchGoogleGmailOAuthUrl();
  if (!url) {
    window.alert(error || "No se pudo iniciar OAuth Gmail.");
    return;
  }
  window.location.href = url;
}
