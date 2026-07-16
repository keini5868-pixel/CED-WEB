/** Planes de suscripción CED */
export type SubscriptionPlanId =
  | "starter"
  | "pro"
  | "elite"
  | "founding"
  | "free_basic"
  | "elite_founding"
  | "elite_regular";

export type UserRole = "client" | "super_admin";

export interface PlanFeatures {
  geminiMinutesPerDay: number;
  webSearchesPerDay: number;
  aiImagesPerDay: number;
  voiceEnabled: boolean;
  cameraEnabled: boolean;
  metaSocialEnabled: boolean;
  prospectionEnabled: boolean;
}

export const FOUNDING_MEMBER_MAX_SLOTS = 50;
export const TRIAL_DAYS = 7;

export const PLAN_PRICES_USD: Record<
  "starter" | "pro" | "elite" | "founding",
  number
> = {
  starter: 30,
  pro: 59,
  elite: 99,
  founding: 149,
};

export const RECHARGE_MARGIN_KEINI = 0.4;
export const RECHARGE_CLIENT_SHARE = 0.6;
/** $0.10/min voz — alineado con API (monedero multi-recurso). */
export const VOICE_COST_PER_MIN_USD = 0.1;
export const IMAGE_STD_COST_USD = 0.02;
export const IMAGE_HD_COST_USD = 0.04;
export const WEB_SEARCH_COST_USD = 0.01;
export const PDF_COST_USD = 0.05;
/** @deprecated usar VOICE_COST_PER_MIN_USD * 60 */
export const GEMINI_COST_PER_HOUR_USD = VOICE_COST_PER_MIN_USD * 60;
export const RECHARGE_MIN_USD = 10;
export const RECHARGE_MAX_USD = 500;
export const RECHARGE_QUICK_AMOUNTS_USD = [10, 20, 40, 50, 100] as const;

/** Capacidades incluidas en todos los planes (sin costo variable de uso). */
export const PLAN_INCLUDED_ALWAYS = [
  "YouTube",
  "Calendario Google",
  "Gmail",
  "Memoria conversacional",
] as const;

export interface RechargeQuote {
  amountPaidUsd: number;
  clientBalanceUsd: number;
  estimatedExtraHours: number;
  estimatedVoiceMinutes: number;
  estimatedImagesStd: number;
  estimatedWebSearches: number;
  estimatedPdfs: number;
  marginKeiniUsd: number;
  neverExpires: true;
}

export function quoteRecharge(amountUsd: number): RechargeQuote {
  const paid = Math.max(RECHARGE_MIN_USD, Math.min(RECHARGE_MAX_USD, amountUsd));
  const clientBalanceUsd = paid * RECHARGE_CLIENT_SHARE;
  const marginKeiniUsd = paid * RECHARGE_MARGIN_KEINI;
  const estimatedVoiceMinutes =
    VOICE_COST_PER_MIN_USD > 0 ? clientBalanceUsd / VOICE_COST_PER_MIN_USD : 0;
  const estimatedExtraHours = estimatedVoiceMinutes / 60;
  return {
    amountPaidUsd: paid,
    clientBalanceUsd: Math.round(clientBalanceUsd * 100) / 100,
    estimatedExtraHours: Math.round(estimatedExtraHours * 100) / 100,
    estimatedVoiceMinutes: Math.floor(estimatedVoiceMinutes),
    estimatedImagesStd: Math.floor(
      IMAGE_STD_COST_USD > 0 ? clientBalanceUsd / IMAGE_STD_COST_USD : 0,
    ),
    estimatedWebSearches: Math.floor(
      WEB_SEARCH_COST_USD > 0 ? clientBalanceUsd / WEB_SEARCH_COST_USD : 0,
    ),
    estimatedPdfs: Math.floor(PDF_COST_USD > 0 ? clientBalanceUsd / PDF_COST_USD : 0),
    marginKeiniUsd: Math.round(marginKeiniUsd * 100) / 100,
    neverExpires: true,
  };
}

const COMMON_FREE_TOOLS = [
  "YouTube",
  "Calendario Google",
  "Gmail",
  "Memoria conversacional",
] as const;

export const PUBLIC_PLANS = [
  {
    id: "free_basic" as const,
    label: "CED Básico",
    priceUsd: 0,
    minutesPerDay: 0,
    highlights: [
      ...COMMON_FREE_TOOLS,
      "Chat de texto",
      "Recarga desde $10 al llegar al límite",
    ],
  },
  {
    id: "starter" as const,
    label: "CED Starter",
    priceUsd: 30,
    minutesPerDay: 15,
    highlights: [
      ...COMMON_FREE_TOOLS,
      "Chat de texto",
      "Asistente de voz CED",
      "Búsquedas web",
      "Creación de imágenes",
    ],
  },
  {
    id: "pro" as const,
    label: "CED Pro",
    priceUsd: 59,
    minutesPerDay: 30,
    highlights: [
      "Todo Starter +",
      ...COMMON_FREE_TOOLS,
      "Asistente de voz CED",
      "Cámara y análisis de imagen",
      "Búsquedas web",
      "Creación de imágenes",
      "Google Maps / navegación",
    ],
  },
  {
    id: "elite" as const,
    label: "CED Élite",
    priceUsd: 99,
    minutesPerDay: 60,
    highlights: [
      "Todo Pro +",
      ...COMMON_FREE_TOOLS,
      "Asistente de voz CED",
      "Instagram / Facebook",
      "Modo prospección",
      "Creación de imágenes",
      "Informes PDF",
      "Modo avanzado",
    ],
  },
  {
    id: "founding" as const,
    label: "CED Founding",
    priceUsd: 149,
    minutesPerDay: 90,
    highlights: [
      "Todo Élite +",
      ...COMMON_FREE_TOOLS,
      "Asistente de voz CED",
      "Precio bloqueado por 6 meses",
      "Creación de imágenes",
      "Cupos limitados",
    ],
  },
] as const;

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

export type GeminiVoiceId = string;

export type VoiceProfileId = "standard" | "jarvis";

export interface VoiceSessionPreferences {
  language: "es" | "en" | "pt";
  responseSpeed: "fast" | "balanced" | "thoughtful";
  voiceName: GeminiVoiceId;
  palette: VoicePaletteId;
  /** 0 = más lento/pausado, 100 = más ágil */
  voicePace: number;
  /** 0 = más formal, 100 = más cálido/cercano */
  voiceWarmth: number;
  /** 0 = más calmada, 100 = más expresiva/energética */
  voiceEnergy: number;
  /** Perfil de personalidad oral (prompt backend) */
  voiceProfile: VoiceProfileId;
}

export const DEFAULT_VOICE_PREFERENCES: VoiceSessionPreferences = {
  language: "es",
  responseSpeed: "balanced",
  voiceName: "echo",
  palette: "cyan",
  voicePace: 35,
  voiceWarmth: 30,
  voiceEnergy: 32,
  voiceProfile: "jarvis",
};

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

export interface UsageBalance {
  planMinutesDaily: number;
  usedMinutesToday: number;
  rechargeBalanceUsd: number;
  bonusMinutesFromBalance: number;
  totalAvailableMinutes: number;
  warningAtPercent: number;
  blocked: boolean;
  needsRecharge?: boolean;
  planId?: SubscriptionPlanId;
  subscriptionStatus?: string;
  trialEndsAt?: string | null;
  isFoundingMember: boolean;
  priceLockedForLife: boolean;
}
