import type { VoiceSessionPreferences } from "@ced/types";

import { DEFAULT_VOICE_PREFERENCES } from "@ced/types";



import { normalizeVoiceName } from "@/lib/voice/geminiVoices";



const PREFS_KEY = "ced_voice_prefs";

const MIC_KEY = "ced_mic_enabled";



type LegacyPrefs = VoiceSessionPreferences & { voiceTone?: "female" | "male" };



function migratePrefs(raw: LegacyPrefs): VoiceSessionPreferences {

  let voiceName = raw.voiceName;

  if (!voiceName && raw.voiceTone) {

    voiceName = raw.voiceTone === "male" ? "Charon" : "Aoede";

  }

  return {

    language: raw.language ?? DEFAULT_VOICE_PREFERENCES.language,

    responseSpeed: raw.responseSpeed ?? DEFAULT_VOICE_PREFERENCES.responseSpeed,

    voiceName: normalizeVoiceName(voiceName),

    palette: raw.palette ?? DEFAULT_VOICE_PREFERENCES.palette,

  };

}



export function loadVoicePreferences(): VoiceSessionPreferences {

  if (typeof window === "undefined") return DEFAULT_VOICE_PREFERENCES;

  try {

    const raw = localStorage.getItem(PREFS_KEY);

    if (!raw) return DEFAULT_VOICE_PREFERENCES;

    return migratePrefs({ ...DEFAULT_VOICE_PREFERENCES, ...JSON.parse(raw) });

  } catch {

    return DEFAULT_VOICE_PREFERENCES;

  }

}



export function saveVoicePreferences(prefs: VoiceSessionPreferences) {

  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));

}



export function loadMicPreference(): boolean {

  if (typeof window === "undefined") return false;

  return localStorage.getItem(MIC_KEY) === "1";

}



export function saveMicPreference(enabled: boolean) {

  localStorage.setItem(MIC_KEY, enabled ? "1" : "0");

}


