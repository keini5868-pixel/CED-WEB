"use client";

"use client";

export type LifeModuleId = "weather" | "events";

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
