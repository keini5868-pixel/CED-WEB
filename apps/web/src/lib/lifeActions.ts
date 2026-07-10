"use client";

import { connectGoogleViaSupabase } from "@/lib/api/google";

export type LifeModuleId = "weather" | "calendar" | "events" | "gmail";

export type LifeActionDetail = {
  /** Prompt opcional — si está vacío, solo abre el chat para escribir. */
  prompt?: string;
  /** Solo true activa micrófono de voz; por defecto false en paneles LIFE. */
  activateVoice?: boolean;
  module?: LifeModuleId;
};

export const CED_LIFE_ACTION_EVENT = "ced-life-action";

/** Abre Chat Normal en modo texto (sin activar voz). */
export function dispatchLifeChatPrompt(prompt?: string, module?: LifeModuleId) {
  window.dispatchEvent(
    new CustomEvent(CED_LIFE_ACTION_EVENT, {
      detail: {
        prompt: prompt?.trim() ?? "",
        activateVoice: false,
        module,
      } satisfies LifeActionDetail,
    }),
  );
}

/** @deprecated Usar dispatchLifeChatPrompt — mantenido por compatibilidad interna. */
export function dispatchLifeVoicePrompt(prompt: string) {
  dispatchLifeChatPrompt(prompt);
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
