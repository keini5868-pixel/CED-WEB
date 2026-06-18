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
export const GEMINI_COST_PER_HOUR_USD = 1.5;
export const RECHARGE_MIN_USD = 10;
export const RECHARGE_MAX_USD = 500;
export const RECHARGE_QUICK_AMOUNTS_USD = [10, 20, 40, 50, 100] as const;

export interface RechargeQuote {
  amountPaidUsd: number;
  clientBalanceUsd: number;
  estimatedExtraHours: number;
  marginKeiniUsd: number;
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

export const PUBLIC_PLANS = [
  {
    id: "starter" as const,
    label: "CED Starter",
    priceUsd: 30,
    minutesPerDay: 15,
    highlights: [
      "Chat texto ilimitado",
      "15 min/día voz CED",
      "30 búsquedas web/día",
      "20 imágenes IA/día",
    ],
  },
  {
    id: "pro" as const,
    label: "CED Pro",
    priceUsd: 59,
    minutesPerDay: 30,
    highlights: [
      "Todo Starter +",
      "30 min/día voz",
      "Cámara por voz",
      "Búsquedas ilimitadas",
      "45 std + 5 HD imágenes/día",
    ],
  },
  {
    id: "elite" as const,
    label: "CED Élite",
    priceUsd: 99,
    minutesPerDay: 60,
    highlights: [
      "Todo Pro +",
      "60 min/día voz",
      "Instagram/Facebook",
      "Modo prospección",
      "95 std + 15 HD imágenes/día",
    ],
  },
  {
    id: "founding" as const,
    label: "CED Founding",
    priceUsd: 149,
    minutesPerDay: 90,
    highlights: [
      "Todo Élite +",
      "90 min/día voz",
      "Precio bloqueado de por vida",
      "145 std + 25 HD imágenes/día",
      "Cupos limitados (50)",
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
