/** Plan único premium CED */
export type SubscriptionPlanId = "elite_founding" | "elite_regular";

export type UserRole = "client" | "super_admin";

/** Características del producto único CED Élite */
export interface CedEliteFeatures {
  geminiLiveMinutesPerDay: number;
  videoAllowed: boolean;
  claudeTextUnlimited: boolean;
  aiImagesPerMonth: number;
  ttsElevenLabs: boolean;
  whisperTranscription: boolean;
  memoryUnlimited: boolean;
  foldersUnlimited: boolean;
  pdfsUnlimited: boolean;
  hudPanelsLive: boolean;
  pwaMobile: boolean;
  prioritySupport: boolean;
  earlyAccessFeatures: boolean;
}

export const CED_ELITE_FEATURES: CedEliteFeatures = {
  geminiLiveMinutesPerDay: 120,
  videoAllowed: true,
  claudeTextUnlimited: true,
  aiImagesPerMonth: 100,
  ttsElevenLabs: true,
  whisperTranscription: true,
  memoryUnlimited: true,
  foldersUnlimited: true,
  pdfsUnlimited: true,
  hudPanelsLive: true,
  pwaMobile: true,
  prioritySupport: true,
  earlyAccessFeatures: true,
};

export const FOUNDING_MEMBER_MAX_SLOTS = 50;

export const PLAN_PRICES_USD: Record<SubscriptionPlanId, number> = {
  elite_founding: 149,
  elite_regular: 249,
};

/** Recarga flexible — saldo en USD de uso (60% del pago va al cliente) */
export const RECHARGE_MARGIN_KEINI = 0.4;
export const RECHARGE_CLIENT_SHARE = 0.6;
export const GEMINI_COST_PER_HOUR_USD = 1.5;
export const RECHARGE_MIN_USD = 5;
export const RECHARGE_MAX_USD = 500;
export const RECHARGE_QUICK_AMOUNTS_USD = [10, 25, 50, 100] as const;

export interface RechargeQuote {
  amountPaidUsd: number;
  clientBalanceUsd: number;
  estimatedExtraHours: number;
  marginKeiniUsd: number;
  /** El saldo de recarga no expira */
  neverExpires: true;
}

export function quoteRecharge(amountUsd: number): RechargeQuote {
  const paid = Math.max(RECHARGE_MIN_USD, Math.min(RECHARGE_MAX_USD, amountUsd));
  const clientBalanceUsd = paid * RECHARGE_CLIENT_SHARE;
  const marginKeiniUsd = paid * RECHARGE_MARGIN_KEINI;
  const estimatedExtraHours =
    GEMINI_COST_PER_HOUR_USD > 0
      ? clientBalanceUsd / GEMINI_COST_PER_HOUR_USD
      : 0;
  return {
    amountPaidUsd: paid,
    clientBalanceUsd: Math.round(clientBalanceUsd * 100) / 100,
    estimatedExtraHours: Math.round(estimatedExtraHours * 100) / 100,
    marginKeiniUsd: Math.round(marginKeiniUsd * 100) / 100,
    neverExpires: true,
  };
}

/** Estados del orbe central JARVIS (Fase 2) */
export type OrbState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "error"
  | "paused";

export const ORB_STATE_LABELS: Record<OrbState, string> = {
  idle: "Listo cuando quieras",
  listening: "Escuchándote… (habla o interrumpe)",
  processing: "Procesando...",
  speaking: "Hablando...",
  error: "Error — intenta de nuevo",
  paused: "En pausa",
};

export type VoicePaletteId = "cyan" | "gold" | "matrix" | "iron";

/** Nombre PrebuiltVoiceConfig de Gemini Live (ej. Aoede, Charon). */
export type GeminiVoiceId = string;

export interface VoiceSessionPreferences {
  language: "es" | "en" | "pt";
  responseSpeed: "fast" | "balanced" | "thoughtful";
  /** Voz Gemini Live — se aplica al abrir/reabrir sesión. */
  voiceName: GeminiVoiceId;
  palette: VoicePaletteId;
}

export const DEFAULT_VOICE_PREFERENCES: VoiceSessionPreferences = {
  language: "es",
  responseSpeed: "fast",
  voiceName: "Charon",
  palette: "cyan",
};

/** Eventos SSE para paneles HUD */
export type HudPanelId = "city" | "global" | "drones" | "waves" | "summary";

export type HudState = "idle" | "searching" | "receiving" | "complete";

export type PanelEvent =
  | { type: "search_started"; query: string }
  | { type: "state"; hud: HudState }
  | {
      type: "panel_item";
      panel: HudPanelId;
      payload: Record<string, unknown>;
    }
  | { type: "summary_chunk"; text: string }
  | { type: "search_complete" };

/** Uso de voz en tiempo real (barra HUD) */
export interface UsageBalance {
  planMinutesDaily: number;
  usedMinutesToday: number;
  /** Saldo USD de recargas (no expira) convertido a minutos disponibles */
  rechargeBalanceUsd: number;
  bonusMinutesFromBalance: number;
  totalAvailableMinutes: number;
  warningAtPercent: number;
  blocked: boolean;
  timezone: string;
  planId: SubscriptionPlanId;
  isFoundingMember: boolean;
  priceLockedForLife: boolean;
}
