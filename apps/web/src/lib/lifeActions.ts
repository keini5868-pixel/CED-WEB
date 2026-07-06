"use client";

import { connectGoogleViaSupabase } from "@/lib/api/google";

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
  const { error } = await connectGoogleViaSupabase("calendar");
  if (error) {
    window.alert(error);
  }
}

export async function connectGoogleGmailFromLife() {
  const { error } = await connectGoogleViaSupabase("gmail");
  if (error) {
    window.alert(error);
  }
}
