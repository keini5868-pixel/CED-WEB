/**
 * Cliente OpenAI Realtime vía WebRTC (recomendado por OpenAI para navegadores).
 * Audio in/out por RTCPeerConnection; eventos y tools por data channel oai-events.
 */

import type { VoiceSessionPreferences } from "@ced/types";

import { fetchDeepAnalysis, fetchGenerateImage, fetchVoiceBrief, negotiateRealtimeCall } from "@/lib/api/openai";
import { fetchSocialComments } from "@/lib/api/social";
import type { UserAddressContext } from "@/lib/api/profile";
import { fetchEphemeralTokenCached } from "@/lib/voice/ephemeralTokenCache";
import { parseCameraIntent } from "@/lib/voice/cameraIntents";
import {
  isProspectionOffIntent,
  isProspectionReportIntent,
  userExplicitlyRequestedProspection,
} from "@/lib/voice/visualSearchIntent";
import { isSocialCommentReadIntent, socialCommentPlatform } from "@/lib/voice/socialCommentIntent";
import { isCasualSocialGreeting } from "@/lib/voice/voiceSmallTalk";
import { cedVoiceError, cedVoiceLog, cedRealtimeLog } from "@/lib/voice/cedVoiceLogger";
import {
  ANALIZAR_CAMARA,
  ACTIVAR_PROSPECCION,
  DESACTIVAR_PROSPECCION,
  REPORTE_PROSPECCION,
  LEER_COMENTARIOS_REDES,
  BUSCAR_MEMORIA,
  CONSULTAR_SISTEMA_AVANZADO,
  GENERAR_PDF,
  GUARDAR_MEMORIA,
  LIVE_TOOL_NAMES,
  PUBLICAR_FACEBOOK,
  PUBLICAR_INSTAGRAM,
  RECALL_PREVIOUS_CONVERSATIONS,
  SAVE_LONG_TERM_MEMORY,
} from "@/lib/voice/liveTools";
import { CED_VOICE_PROFILE_LOCK } from "@/lib/voice/live/voice-profile.lock";
import { isBenignRealtimeError } from "@/lib/voice/realtimeErrors";
import {
  isInputTranscriptionCompleted,
  isResponseAudioDone,
  isResponseAudioTranscriptDelta,
} from "@/lib/voice/realtimeEvents";
import { voiceTelemetry } from "@/lib/voice/voiceTelemetry";
import {
  cedBriefTurn,
  cedPublishConfirmTurn,
  cedPublishFailurePhrase,
  cedPublishSuccessPhrase,
  cedReceptionGreetingPhrase,
  cedAdvancedBriefTurn,
  cedResolveHonorific,
  CED_ADVANCED_CONFIRM_PHRASE,
} from "@/lib/voice/live/ced-brief-messages";

const TOOL_ALIAS: Record<string, string> = {
  save_memory: GUARDAR_MEMORIA,
  recall_memory: BUSCAR_MEMORIA,
  recall_previous_conversations: RECALL_PREVIOUS_CONVERSATIONS,
  save_to_long_term_memory: SAVE_LONG_TERM_MEMORY,
  generar_pdf: GENERAR_PDF,
  consultar_claude: CONSULTAR_SISTEMA_AVANZADO,
  analyze_camera_frame: ANALIZAR_CAMARA,
  publish_to_social: "publicar_facebook",
};

function normalizeToolInvocation(
  rawName: string,
  args: Record<string, unknown>,
): { name: string; args: Record<string, unknown> } {
  if (rawName === "publish_to_social") {
    const platform = String(args.platform ?? "facebook").toLowerCase();
    const content = String(
      args.content ?? args.message ?? args.mensaje ?? args.texto ?? "",
    ).trim();
    if (platform === "instagram") {
      return {
        name: "publicar_instagram",
        args: { ...args, caption: content || args.caption },
      };
    }
    return {
      name: "publicar_facebook",
      args: { ...args, mensaje: content || args.mensaje },
    };
  }
  return { name: TOOL_ALIAS[rawName] ?? rawName, args };
}

export type GeminiCloseInfo = {
  unexpected: boolean;
  recoverable: boolean;
  userMessage?: string;
  code?: number;
};

export type CedLiveConnectOptions = {
  voiceName?: string;
  language?: VoiceSessionPreferences["language"];
  responseSpeed?: VoiceSessionPreferences["responseSpeed"];
  voicePace?: VoiceSessionPreferences["voicePace"];
  voiceWarmth?: VoiceSessionPreferences["voiceWarmth"];
  voiceEnergy?: VoiceSessionPreferences["voiceEnergy"];
  voiceProfile?: VoiceSessionPreferences["voiceProfile"];
  /** Stream de micrófono con echoCancellation (WebRTC uplink). */
  micStream: MediaStream;
};

export type CedLiveHandlers = {
  onState?: (state: "connecting" | "connected" | "closed" | "error") => void;
  onSessionReady?: () => void;
  /** Saludo inicial terminado — habilitar escucha normal. */
  onGreetingComplete?: () => void;
  onTranscriptUpdate?: (text: string, role: "user" | "model") => void;
  onTranscript?: (text: string, role: "user" | "model") => void;
  /** WebRTC reproduce audio remoto; callback opcional para UI (inicio de respuesta). */
  onResponseStart?: () => void;
  /** Audio remoto terminó de transmitirse (antes de response.done). */
  onModelAudioDone?: () => void;
  onTurnComplete?: () => void;
  onInterrupted?: () => void;
  onSpeechStopped?: () => void;
  onToolStart?: (toolName: string) => void;
  onToolComplete?: () => void;
  onCameraIntent?: (intent: "activate" | "deactivate") => void;
  /** Tool request_camera_activation / deactivation desde OpenAI. */
  onCameraTool?: (intent: "activate" | "deactivate") => Promise<boolean>;
  onError?: (message: string) => void;
  onClose?: (info: GeminiCloseInfo) => void;
  shouldAllowAdvancedTool?: (toolPrompt: string) => boolean;
  onAdvancedToolBlocked?: (toolPrompt: string) => void;
  onLiveTool?: (
    name: string,
    args: Record<string, unknown>,
  ) => Promise<{ spoken?: string; ok?: boolean } | void>;
  onGeneratedImage?: (url: string, prompt?: string) => void;
  /** Resuelve imagen de referencia (cámara, última imagen, adjunto) para generate_image_with_reference. */
  onGenerateImageWithReference?: (
    args: Record<string, unknown>,
  ) => Promise<{ ok: boolean; url?: string; error?: string; spoken?: string }>;
  /** Ejecuta lectura de comentarios sin depender del modelo. */
  onSocialCommentsIntent?: (utterance: string) => void;
  /** Activa prospección con una sola voz (sin duplicar tool del modelo). */
  onProspectionIntent?: (utterance: string) => void;
};

function classifyPeerClose(unexpected: boolean): GeminiCloseInfo {
  if (!unexpected) {
    return { unexpected: false, recoverable: false };
  }
  return {
    unexpected: true,
    recoverable: true,
    userMessage: undefined,
  };
}

export class CedLiveClient {
  private pc: RTCPeerConnection | null = null;
  private dc: RTCDataChannel | null = null;
  private remoteAudio: HTMLAudioElement | null = null;
  private micStream: MediaStream | null = null;
  private sessionReady = false;
  private connectGen = 0;
  private connectInFlight = false;
  private intentionalClose = false;
  private sendBlocked = true;
  private model = "";
  private userTranscriptAcc = "";
  private modelTranscriptAcc = "";
  private processedCallIds = new Set<string>();
  private recentToolAt = new Map<string, number>();
  private activeResponseId: string | null = null;
  private responseInProgress = false;
  private videoStream: MediaStream | null = null;
  private videoSender: RTCRtpSender | null = null;
  private lastVideoFrameAt = 0;
  private static TOOL_COOLDOWN_MS = 2000;
  private static RESPONSE_IDLE_MS = 3200;
  private static VIDEO_FRAME_MIN_MS = 2000;
  private voiceProfile: VoiceSessionPreferences["voiceProfile"] = "jarvis";
  private userAddress: UserAddressContext | null = null;
  private handlers: CedLiveHandlers = {};
  private greetingSent = false;
  private greetingInFlight = false;
  private greetingComplete = false;
  private heardUserSinceGreeting = false;
  private greetingGraceUntil = 0;
  private outboundLocked = false;
  private awaitingFirstUserSpeech = false;
  private userTurnScheduled = false;
  private userResponseTimer: number | null = null;
  private intentionalResponse = false;
  private intentionalResponseActive = false;
  private blockAutoResponsesUntil = 0;
  /** "open" = esperando un response.id; string = único permitido; "closed" = normal */
  private singleSpeechSlot: "closed" | "open" | string = "closed";
  private userMicLive = false;
  private lastMeaningfulUserUtterance = "";
  private advancedBriefInFlight = false;
  private userTurnResponded = false;
  private lastArmedTranscript = "";
  private turnCooldownUntil = 0;
  private lastResponseCreateAt = 0;
  private briefChain: Promise<void> = Promise.resolve();
  private toolsEnabled = true;
  private modelAudioDoneResolve: (() => void) | null = null;
  /** Autoriza un único response.create tras intervención real del usuario. */
  private userResponseArmed = false;
  private postGreetingLockUntil = 0;
  /** Tras saludo: OpenAI server_vad + create_response maneja el turno. */
  private serverConversationMode = false;
  /** Espera primer transcript real antes de create_response automático. */
  private waitingForFirstUserInput = false;
  private lastGreetingPhrase = "";
  private greetingCompletedAt = 0;
  /** Última utterance del modelo (para filtrar eco del propio audio). */
  private lastCompletedModelUtterance = "";
  private lastModelSpeechAt = 0;
  /** speakExactPhrase cancelado por fuga de instrucciones. */
  private exactPhraseLeak = false;
  /** Frase que speakExactPhrase debe leer (para detectar paráfrasis). */
  private exactPhraseExpected = "";
  /** Ya hubo audio usable en el intento actual — no reintentar (evita apilar). */
  private exactPhraseHadUsableAudio = false;
  /** Tras primer turno: activar server create_response al terminar esta respuesta. */
  private pendingEnableAutoAfterResponse = false;

  private static SERVER_VAD = {
    threshold: 0.5,
    prefix_padding_ms: 300,
    silence_duration_ms: 500,
    interrupt_response: true,
  } as const;

  isGreetingInProgress(): boolean {
    return (
      this.greetingInFlight ||
      (!this.greetingComplete && this.greetingSent) ||
      Date.now() < this.greetingGraceUntil
    );
  }

  /** Quita ¡¿ y puntuación para filtrar «¡Gracias!» / eco TV. */
  private normalizeSpeechTokens(text: string): string {
    return text
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[¡¿]/g, "")
      .replace(/[.,!?;:…"""«»]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  /** Frases fantasma que Whisper inventa con silencio/eco — no son el usuario. */
  private isWhisperHallucination(text: string): boolean {
    const t = this.normalizeSpeechTokens(text);
    if (!t) return true;
    if (t.length <= 3) return true;
    return (
      /amara\.org|subt[ií]tulos realizados|subtitles by|thanks for watching|thank you for watching|for more information|visit www\.|copyright|\bwww\./i.test(
        t,
      ) ||
      /^you$/i.test(t) ||
      /^thank you$/i.test(t) ||
      /^\s*\(?music\)?\s*$/i.test(t)
    );
  }

  /** Gracias / ok / hola sueltos — no abren conversación ni plan de franquicia. */
  private isSocialFillerSpeech(transcript: string): boolean {
    const t = this.normalizeSpeechTokens(transcript);
    if (!t) return true;
    if (/^(muchas|muchisimas|mil)?\s*gracias(\s+(señor|senor|señora|senora))?$/.test(t)) {
      return true;
    }
    if (/^(thanks|thank you|ty|ok|okay|vale|dale|listo|perfecto|claro|bueno|de acuerdo|entendido)(\s+(señor|senor|señora|senora))?$/.test(t)) {
      return true;
    }
    if (/^(hola|hey|buenas|saludos|buen dia|buenos dias|buenas tardes|buenas noches)(\s+(señor|senor|señora|senora|ced))?$/.test(t)) {
      return true;
    }
    if (/^(hola\s+)?(como estas|que tal|como te va|todo bien)(\s+(señor|senor|señora|senora))?$/.test(t)) {
      return true;
    }
    return false;
  }

  private isLikelyBackgroundNoise(transcript: string): boolean {
    const raw = transcript.trim().toLowerCase();
    if (!raw || /^<noise>$/i.test(raw)) return true;
    if (this.isWhisperHallucination(raw)) return true;
    if (this.isSocialFillerSpeech(raw)) return true;
    const t = this.normalizeSpeechTokens(raw);
    if (/^entendido\s*señor$/.test(t)) return true;
    if (/^(chau|chao|adios|bye|goodbye|nos vemos|hasta luego)$/.test(t)) return true;
    if (/^(un besito|besito|un abrazo|te quiero|mi amor)$/.test(t)) return true;
    return (
      /gracias por ver|por ver el video|hasta la pr[oó]xima|nos vemos en|pr[oó]ximo video|suscr[ií]bete|suscr[ií]bete al canal|dale like|deja tu like|thanks for watching|see you in the next|don't forget to subscribe|subscribe to|much[ií]simas gracias|activar la c[aá]mara|voy a activar|c[aá]mara activa|amara\.org|subt[ií]tulos|subtitulos|realizados por|comunidad de amara|realizada por la comunidad/i.test(
        raw,
      )
    );
  }

  /** Eco del system/response prompt — cancelar de inmediato. */
  private isPromptInstructionLeak(text: string): boolean {
    const low = text.toLowerCase();
    return (
      /puedo repetir|exactamente como me lo dic|di exactamente|palabra por palabra|entre <<<|<<<|>>>|modo lectura|text-to-speech|estas instrucciones|el texto siguiente|lee en voz alta una sola vez|\[ced_greeting\]|\[ced_brief\]|\bfrase\s*:/i.test(
        low,
      ) ||
      (/s[ií],?\s*claro/.test(low) && /repetir|exactamente|instrucci/i.test(low))
    );
  }

  /** Segundo saludo del modelo o muletilla — cortar de inmediato. */
  private isRogueModelGreeting(text: string): boolean {
    const trimmed = text.trim();
    if (!trimmed || /^[,.\s…]{1,8}$/.test(trimmed)) return true;
    if (this.outboundLocked) {
      // Durante speakExactPhrase aún cancelamos fugas de prompt.
      return this.isPromptInstructionLeak(trimmed);
    }
    if (this.isPromptInstructionLeak(trimmed)) return true;
    const low = text.toLowerCase();
    if (/^[\s.,]*(me enc|encantado|encantada)\b/i.test(trimmed)) return true;
    if (
      /c[oó]mo te gustar[ií]a|prefieres que use|tratamiento formal|en lo que necesites|qu[eé] prefieres/i.test(
        low,
      )
    ) {
      return true;
    }
    // Inglés espontáneo o muletillas — cortar (paridad Retell ES).
    if (
      /\b(hi there|what'?s on your mind|how can i help|how may i help|good (morning|afternoon|evening)[!.,]?\s*(how can|what)|sure[,!]?\s*sure|claro,?\s*claro)\b/i.test(
        low,
      )
    ) {
      return true;
    }
    // Nombre inventado / saludo largo tipo «Mire, Leroy…» (no «Mire, señor»).
    if (/\bmire[,.]?\s+(?!se[nñ]or|se[nñ]ora|usted|don|do[nñ]a)([a-záéíóúñ]{3,})/i.test(low)) {
      const known = (
        this.userAddress?.firstName ||
        this.userAddress?.displayName ||
        ""
      )
        .trim()
        .toLowerCase();
      const m = low.match(
        /\bmire[,.]?\s+(?!se[nñ]or|se[nñ]ora|usted|don|do[nñ]a)([a-záéíóúñ]+)/i,
      );
      const said = (m?.[1] || "").toLowerCase();
      if (said && (!known || !known.includes(said))) {
        return true;
      }
    }
    // Saludo temático incorrecto (import/mercadería) — nunca al conectar.
    if (
      (this.awaitingFirstUserSpeech || !this.heardUserSinceGreeting) &&
      /mercader[ií]a|necesitas importar|quiere[sn]? importar|qu[eé] producto.*(import|comprar|necesitas)|producto de mercader|cat[aá]logo gen[eé]rico/i.test(
        low,
      )
    ) {
      return true;
    }
    // Cuestionario de plan/franquicia o re-saludo sin que el usuario haya hablado.
    if (this.awaitingFirstUserSpeech || !this.heardUserSinceGreeting) {
      if (
        /principal meta|detalle.*incluir.*plan|aspecto espec[ií]fico.*franquicia|aumentar clientes|p[uú]blico objetivo|en qu[eé] te gustar[ií]a|c[oó]mo est[aá]s|cu[eé]ntame.*ayud|qu[eé] te gustar[ií]a que te ayude|clar[oa],?\s+por favor dime|crecimiento de la franquicia/i.test(
          low,
        )
      ) {
        return true;
      }
    }
    if (/activando.*prosp|activando ahora|entendido.*activando|modo prosp|prospecci[oó]n activada|queda registrado,\s*s[ií]/i.test(low)) {
      if (this.awaitingFirstUserSpeech || !this.heardUserSinceGreeting) return true;
      if (!userExplicitlyRequestedProspection(this.lastMeaningfulUserUtterance)) return true;
    }
    const rogue =
      /buenas tardes|buen d[ií]a|buenos d[ií]as|muy buenas|un placer saludar|encantado de saludar|estoy aqu[ií] para ayudar|listo para ayudar|qu[eé] tiene en mente|en qu[eé] le gustar[ií]a|aqu[ií] estoy[,]? listo|en qu[eé] trabajamos|en qu[eé] puedo ayudar|saludarte|encantado de|adelante[,]? estoy a la escucha|estoy a la escucha|qu[eé] necesitas ahora|listo para escuchar|dime qu[eé] necesitas|entendido[,.]? activando|activando el modo prosp/i.test(
        low,
      );
    if (!rogue && !/^hola[,]?\s*(señor|señora|senor|senora)/i.test(low)) return false;
    // Solo antes del primer turno real del usuario — después "¿en qué puedo ayudar?"
    // es lenguaje normal de FitLine/CED y no debe cancelar la respuesta.
    if (this.awaitingFirstUserSpeech || !this.heardUserSinceGreeting) return true;
    if (/^hola,?\s*(señor|señora|senor|senora).*en qu[eé] puedo ayudarle/i.test(low)) return true;
    if (
      /^(buenas tardes|buen d[ií]a|buenos d[ií]as|muy buenas)\b/i.test(low) &&
      trimmed.length < 90
    ) {
      return true;
    }
    return false;
  }

  isRogueModelOutput(text: string): boolean {
    return this.isRogueModelGreeting(text);
  }

  private isClientAuthorizedResponse(): boolean {
    return (
      this.outboundLocked ||
      this.intentionalResponseActive ||
      this.userResponseArmed ||
      this.advancedBriefInFlight
    );
  }

  /** Solo intervención real del usuario — TV/subtítulos/frases sueltas NO cuentan. */
  private isMeaningfulUserSpeech(transcript: string): boolean {
    const t = transcript.trim();
    if (!t || this.isLikelyAmbientOrEcho(t)) return false;
    if (this.isSocialFillerSpeech(t) || this.isLikelyBackgroundNoise(t)) return false;
    const low = this.normalizeSpeechTokens(t);
    if (/^(ahora\s+si|si|ok|vale|dale|perfecto|claro|bueno|listo|de acuerdo)$/.test(low)) {
      return false;
    }
    if (/^(muchas|muchisimas)?\s*gracias/.test(low) && low.length < 50) return false;
    // FitLine / PM — productos y negocio (Cierre $20): no filtrar como ruido.
    if (
      /\b(pm[\s\-]?international|p\.?\s*m\.?\s*i|fitline|fit\s*line|restorate|restore|activize|activise|activis|power\s*cocktail|powercocktail|optimal[\s\-]?set|ntc|franquicia|patrocinio|cologne|nutriente|minerales|oxipl[uú]s|oxyplus)\b/i.test(
        low,
      )
    ) {
      return true;
    }
    if (
      /\b(publicar|clima|comentario|comentarios|facebook|instagram|guion|guion|pdf|imagen|camara|busca|ayuda|publica|hora|tiempo|ced|fitline|fit\s*line|cierre|venta|ventas|cliente|prospecto|producto|empresa|negocio)\b/i.test(
        low,
      ) ||
      /\b(activar|modo)\s+prospecci/i.test(low)
    ) {
      return true;
    }
    if (parseCameraIntent(t)) return true;
    if (/\?/.test(t) && t.length >= 12) return true;
    if (
      /^(que|como|donde|cuando|cuanto|quien|por que|porque|ahora|hablame|hableme)\b/i.test(
        low,
      ) &&
      t.length >= 12
    ) {
      return true;
    }
    if (
      /\b(necesito|quiero|explicame|explicame|hablar|empezar|empezamos|saber|sobre)\b/i.test(
        low,
      ) &&
      t.length >= 12
    ) {
      return true;
    }
    if (
      t.length >= 16 &&
      /\b(por favor|necesito|quiero|dime|dejame|muestrame|explicame|lee|leer|publica|genera|cuentame)\b/i.test(
        low,
      )
    ) {
      return true;
    }
    // Frase corta con verbo de pedido — típico tras saludo FitLine.
    if (t.length >= 10 && /\b(necesito|quiero|puedes|podrias|ayuda|ayudame)\b/i.test(low)) {
      return true;
    }
    // FitLine: exigir contenido real — NO cualquier eco/alucinación de 8 letras.
    if (
      this.voiceProfile === "fitline" &&
      t.length >= 18 &&
      /\b(plan|meta|cliente|ingreso|producto|restorate|activize|fitline|franquicia|negocio|pm|vender|venta|equipo|patrocin)\b/i.test(
        low,
      )
    ) {
      return true;
    }
    return false;
  }

  private normalizeEchoText(text: string): string {
    return text
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^\p{L}\p{N}\s]/gu, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  /** Eco del audio de CED captado por el mic (durante o justo después de hablar). */
  private isEchoOfOwnSpeech(transcript: string): boolean {
    const t = this.normalizeEchoText(transcript);
    if (t.length < 6) return false;
    const recent =
      this.responseInProgress || Date.now() - this.lastModelSpeechAt < 4_500;
    if (!recent && !this.awaitingFirstUserSpeech) return false;
    const sources = [
      this.modelTranscriptAcc,
      this.lastCompletedModelUtterance,
      this.lastGreetingPhrase,
    ];
    for (const src of sources) {
      const m = this.normalizeEchoText(src);
      if (m.length < 8) continue;
      if (m.includes(t) || t.includes(m.slice(0, Math.min(48, m.length)))) {
        return true;
      }
      const tWords = t.split(" ").filter((w) => w.length > 3);
      const mSet = new Set(m.split(" ").filter((w) => w.length > 3));
      if (tWords.length >= 2) {
        const hits = tWords.filter((w) => mSet.has(w)).length;
        if (hits / tWords.length >= 0.55) return true;
      }
    }
    return false;
  }

  private isLikelyAmbientOrEcho(transcript: string): boolean {
    if (this.isLikelyBackgroundNoise(transcript)) return true;
    if (this.isLikelyGreetingEcho(transcript)) return true;
    if (this.isEchoOfCedGreeting(transcript)) return true;
    if (this.isEchoOfOwnSpeech(transcript)) return true;
    const low = transcript.toLowerCase();
    return (
      (low.includes("buenos días") || low.includes("buenos dias")) &&
      (low.includes("ced") || low.includes("asistir"))
    ) || low.includes("listo para asistir") || low.includes("aquí ced");
  }

  /** ¿El audio leído se parece a la frase exacta pedida? */
  private spokenMatchesExactPhrase(expected: string, spoken: string): boolean {
    const e = this.normalizeEchoText(expected);
    const s = this.normalizeEchoText(spoken);
    if (!s || s.length < 4) return true; // sin transcript: no forzar reintento
    if (e.length >= 10 && (s.includes(e.slice(0, 18)) || e.includes(s.slice(0, 18)))) {
      return true;
    }
    const eWords = e.split(" ").filter((w) => w.length > 2);
    const sSet = new Set(s.split(" ").filter((w) => w.length > 2));
    if (eWords.length < 3) return s.includes(eWords[0] ?? "");
    const hits = eWords.filter((w) => sSet.has(w)).length;
    return hits / eWords.length >= 0.45;
  }

  private beginSingleSpeechSlot(): void {
    this.singleSpeechSlot = "open";
  }

  private endSingleSpeechSlot(): void {
    this.singleSpeechSlot = "closed";
  }

  private cancelResponse(responseId?: string | null): void {
    if (responseId) {
      this.send({ type: "response.cancel", response_id: responseId });
    } else {
      this.triggerBargeIn();
    }
  }

  /** Permite respuestas nativas; solo bloquea ventana de saludo y duplicados. */
  private allowResponseCreated(responseId?: string | null): boolean {
    const id = responseId ?? null;

    if (
      (this.greetingInFlight || !this.greetingComplete || Date.now() < this.greetingGraceUntil) &&
      !this.intentionalResponseActive
    ) {
      cedRealtimeLog("response.reject.greeting_window", { id });
      this.cancelResponse(id);
      return false;
    }

    if (this.waitingForFirstUserInput && !this.intentionalResponseActive) {
      cedRealtimeLog("response.reject.awaiting_first_user", { id });
      this.cancelResponse(id);
      return false;
    }

    if (this.singleSpeechSlot !== "closed") {
      if (this.singleSpeechSlot === "open") {
        this.singleSpeechSlot = id ?? "unknown";
        return true;
      }
      if (id && this.singleSpeechSlot !== id) {
        cedRealtimeLog("response.reject.duplicate", { id, allowed: this.singleSpeechSlot });
        this.cancelResponse(id);
        return false;
      }
      return true;
    }

    if (!this.userMicLive && !this.outboundLocked && !this.intentionalResponse) {
      cedRealtimeLog("response.reject.mic_off", { id });
      this.cancelResponse(id);
      return false;
    }

    if (this.responseInProgress && this.activeResponseId && id && id !== this.activeResponseId) {
      cedRealtimeLog("response.dedupe.cancel", { id });
      this.cancelResponse(id);
      return false;
    }
    return true;
  }

  /** Tras saludo: escucha sin autorespuesta hasta primer transcript del usuario. */
  enableListeningAfterGreeting(): void {
    if (!this.sessionReady || this.sendBlocked) return;
    this.flushInputAudioBuffer();
    this.userMicLive = true;
    this.serverConversationMode = true;
    this.waitingForFirstUserInput = true;
    // Crítico: no dejar grace/post-lock activos — cancelaban el primer turno del usuario.
    this.greetingGraceUntil = 0;
    this.postGreetingLockUntil = 0;
    this.blockAutoResponsesUntil = 0;
    this.applyTurnDetection("manual");
  }

  /** Activa create_response tras primera intervención real del usuario. */
  private onFirstUserTranscript(transcript: string): boolean {
    if (!this.waitingForFirstUserInput) return false;
    if (!this.isMeaningfulUserSpeech(transcript)) return false;
    if (this.isEchoOfCedGreeting(transcript)) {
      cedRealtimeLog("transcript.greeting_echo_ignored", { transcript: transcript.slice(0, 80) });
      this.flushInputAudioBuffer();
      return false;
    }
    // Evitar eco inmediato del saludo (~1s basta; 2.5s + unmute 2.8s dejaba sordo el turno).
    if (Date.now() - this.greetingCompletedAt < 900) return false;
    this.waitingForFirstUserInput = false;
    this.greetingGraceUntil = 0;
    this.blockAutoResponsesUntil = 0;
    // Mantener VAD manual en ESTE turno — auto create_response del server
    // chocaba con nuestro response.create → "active response in progress".
    this.pendingEnableAutoAfterResponse = true;
    this.applyTurnDetection("manual");
    cedRealtimeLog("turn_detection.first_user_armed", {
      transcript: transcript.slice(0, 60),
    });
    return true;
  }

  /** Un solo response.create — cancela/espera si ya hay uno en curso. */
  private async safeResponseCreate(
    payload?: Record<string, unknown>,
  ): Promise<boolean> {
    if (!this.dc || this.dc.readyState !== "open" || this.sendBlocked) return false;
    if (this.responseInProgress || this.activeResponseId) {
      cedRealtimeLog("response.create.wait_or_cancel", {
        active: this.activeResponseId,
      });
      this.triggerBargeIn();
      await this.waitForResponseIdle(1500);
    }
    if (this.responseInProgress) {
      cedRealtimeLog("response.create.skipped_busy", {});
      return false;
    }
    const now = Date.now();
    if (now - this.lastResponseCreateAt < 700) {
      cedRealtimeLog("response.create.skipped_debounce", {});
      return false;
    }
    this.lastResponseCreateAt = now;
    this.responseInProgress = true;
    this.userTurnResponded = true;
    this.userResponseArmed = true;
    this.intentionalResponse = true;
    this.intentionalResponseActive = true;
    cedRealtimeLog("response.create.safe", {
      utterance: this.lastMeaningfulUserUtterance.slice(0, 60),
    });
    this.send({
      type: "response.create",
      ...(payload ? { response: payload } : {}),
    });
    return true;
  }

  /** Pausa — corta voz y deja de escuchar. */
  hardPause(): void {
    this.userMicLive = false;
    this.triggerBargeIn();
    this.applyTurnDetection("off");
    this.clearUserResponseTimer();
    this.flushInputAudioBuffer();
    this.setRemoteMuted(true);
    this.endSingleSpeechSlot();
  }

  /** Reanuda escucha tras pausa. */
  resumeListening(): void {
    if (!this.sessionReady || this.sendBlocked) return;
    this.setRemoteMuted(false);
    this.userMicLive = true;
    this.blockAutoResponsesUntil = 0;
    this.applyTurnDetection(
      this.serverConversationMode
        ? this.waitingForFirstUserInput
          ? "manual"
          : "auto"
        : "listen",
    );
    this.flushInputAudioBuffer();
  }

  getLastMeaningfulUserUtterance(): string {
    return this.lastMeaningfulUserUtterance;
  }

  userExplicitlyRequestedVision(): boolean {
    const last = this.lastMeaningfulUserUtterance.trim();
    if (!last) return false;
    if (parseCameraIntent(last) === "activate") return true;
    return /\b(c[aá]mara|camara|mira esto|qu[eé] ves|qu[eé] veo|mostrar|enseñar|vision|visi[oó]n|foto|imagen)\b/i.test(
      last,
    );
  }

  private isLikelyGreetingEcho(transcript: string): boolean {
    if (!this.awaitingFirstUserSpeech && this.heardUserSinceGreeting) return false;
    const low = this.normalizeSpeechTokens(transcript);
    if (!low) return true;
    if (
      /\ba\s+su\s+servicio\b/.test(low) ||
      /\boperativo\b.*\bservicio\b/.test(low) ||
      /\bservicio\b.*\bse[nñ]or/.test(low) ||
      /\bsi,?\s*(senor|senora|don|dona)\b/.test(low) ||
      /\ben\s+que\s+(lo|la|te)\s+puedo\s+ayudar\b/.test(low) ||
      /\ben\s+que\s+puedo\s+ayudarle\b/.test(low) ||
      /\bcomo\s+est[aá]s?\b/.test(low) ||
      /\bel\s+dia\s+de\s+hoy\b/.test(low)
    ) {
      return true;
    }
    if (this.lastGreetingPhrase) {
      const gl = this.normalizeSpeechTokens(this.lastGreetingPhrase);
      if (gl.length >= 8 && low.length >= 6) {
        if (gl.includes(low) || low.includes(gl.slice(0, Math.min(24, gl.length)))) {
          return true;
        }
        const gWords = gl.split(" ").filter((w) => w.length > 2);
        const lSet = new Set(low.split(" ").filter((w) => w.length > 2));
        if (gWords.length >= 3) {
          const hits = gWords.filter((w) => lSet.has(w)).length;
          if (hits / gWords.length >= 0.5) return true;
        }
      }
    }
    return (
      low.includes("hola") &&
      (low.includes("senor") ||
        low.includes("senora") ||
        low.includes("ayudar") ||
        low.includes("como esta") ||
        low.includes("como estas"))
    );
  }

  /** Eco del saludo de CED captado por el micrófono — no es el usuario. */
  private isEchoOfCedGreeting(transcript: string): boolean {
    // Ventana post-saludo ampliada: el eco puede llegar tras unmute.
    const postGreetingMs = Date.now() - this.greetingCompletedAt;
    const inPostGreetingWindow =
      this.awaitingFirstUserSpeech ||
      this.waitingForFirstUserInput ||
      (this.greetingComplete && postGreetingMs >= 0 && postGreetingMs < 8_000);
    if (!inPostGreetingWindow) return false;
    if (this.isLikelyGreetingEcho(transcript)) return true;
    const low = this.normalizeSpeechTokens(transcript);
    if (
      /\boperativo\b/.test(low) ||
      /\ba\s+la\s+espera\b/.test(low) ||
      (/\bservicio\b/.test(low) && /\bsenor/.test(low))
    ) {
      return true;
    }
    return false;
  }

  private phraseForCasualSocial(transcript: string): string | null {
    if (!isCasualSocialGreeting(transcript)) return null;
    const h = this.resolveHonorific();
    const low = transcript.toLowerCase();
    if (/^(un\s+)?saludos?[\s.!?,]*$/i.test(transcript.trim())) {
      return `Buenos días, ${h}.`;
    }
    if (/\b(c[oó]mo est[aá]s|qu[eé] tal|c[oó]mo te va)\b/i.test(low)) {
      return `Operativo y a su servicio, ${h}.`;
    }
    if (/^hola[\s.!?,]*$/i.test(transcript.trim())) {
      return `Buenos días, ${h}.`;
    }
    return `Operativo y a su servicio, ${h}.`;
  }

  private async handleCasualSocialTurn(phrase: string): Promise<void> {
    if (this.waitingForFirstUserInput) {
      this.waitingForFirstUserInput = false;
      this.pendingEnableAutoAfterResponse = true;
      this.applyTurnDetection("manual");
    }
    if (this.responseInProgress) {
      this.triggerBargeIn();
      await this.waitForResponseIdle(1200);
    }
    await this.speakExactPhrase(phrase, 72);
  }

  private markUserSpeechHeard(transcript: string): void {
    if (!this.isMeaningfulUserSpeech(transcript)) return;
    if (this.awaitingFirstUserSpeech) {
      this.awaitingFirstUserSpeech = false;
    }
    this.heardUserSinceGreeting = true;
    this.lastMeaningfulUserUtterance = transcript.trim();
    this.blockAutoResponsesUntil = 0;
  }

  private resolveHonorific(): string {
    return cedResolveHonorific(this.userAddress);
  }

  private briefTokensForSpoken(spoken: string, advanced = false): number {
    const min = advanced ? 680 : 180;
    return Math.min(900, Math.max(min, Math.ceil(spoken.length / 2.8)));
  }

  /** Respuesta fija a "bien/gracias" — desactivado: provocaba loops con audio de TV. */

  /** Respuesta inmediata tras transcripción válida del usuario. */
  private requestSingleResponse(): void {
    const now = Date.now();
    if (!this.userMicLive || this.responseInProgress || this.outboundLocked) return;
    if (now < this.blockAutoResponsesUntil) return;
    if (now < this.greetingGraceUntil) return;
    if (!this.heardUserSinceGreeting || !this.lastMeaningfulUserUtterance) return;
    if (this.userTurnResponded && now - this.lastResponseCreateAt < 2500) return;
    if (now - this.lastResponseCreateAt < 700) return;
    this.postGreetingLockUntil = 0;
    this.turnCooldownUntil = now + 2500;
    void this.safeResponseCreate({
      max_output_tokens: this.voiceProfile === "fitline" ? 1400 : 900,
    });
  }

  private triggerUserResponse(): void {
    // En modo servidor: el primer turno lo arma onFirstUserTranscript; si ya pasó,
    // aún así pedimos respuesta (create_response a veces no dispara en WebRTC).
    if (this.serverConversationMode && this.waitingForFirstUserInput) return;
    const utterance = this.lastMeaningfulUserUtterance;
    if (!this.isMeaningfulUserSpeech(utterance)) return;
    if (isCasualSocialGreeting(utterance)) return;
    if (isSocialCommentReadIntent(utterance)) {
      this.userTurnResponded = true;
      this.handlers.onSocialCommentsIntent?.(utterance);
      return;
    }
    if (userExplicitlyRequestedProspection(utterance)) {
      this.userTurnResponded = true;
      this.handlers.onProspectionIntent?.(utterance);
      return;
    }
    this.requestSingleResponse();
  }

  private clearUserResponseTimer(): void {
    if (this.userResponseTimer) {
      window.clearTimeout(this.userResponseTimer);
      this.userResponseTimer = null;
    }
  }

  /** Sesión Realtime creada sin herramientas (fallback API). */
  isToolsEnabled(): boolean {
    return this.toolsEnabled;
  }

  isOpen(): boolean {
    return Boolean(this.pc && this.sessionReady && !this.sendBlocked);
  }

  isResponseActive(): boolean {
    return this.responseInProgress;
  }

  /** Libera estado colgado si response.done no llegó (WebRTC). */
  forceReleaseTurn(): void {
    if (!this.responseInProgress && !this.activeResponseId) return;
    cedVoiceLog(4, "forceReleaseTurn — liberando respuesta colgada");
    this.activeResponseId = null;
    this.responseInProgress = false;
    this.intentionalResponse = false;
    this.intentionalResponseActive = false;
    this.userResponseArmed = false;
    this.endSingleSpeechSlot();
    this.flushInputAudioBuffer();
  }

  /** Tras acción directa del cliente (comentarios, prospección) — reabrir escucha. */
  releaseTurnAfterClientAction(): void {
    this.forceReleaseTurn();
    this.blockAutoResponsesUntil = 0;
    this.turnCooldownUntil = 0;
    this.userTurnResponded = false;
    this.outboundLocked = false;
    this.endSingleSpeechSlot();
    this.flushInputAudioBuffer();
  }

  /** Compat — WebRTC maneja half-duplex con AEC nativo. */
  setBlockServerVad(_block: boolean): void {
    void _block;
  }

  setMicTrackEnabled(enabled: boolean): void {
    this.micStream?.getAudioTracks().forEach((t) => {
      t.enabled = enabled;
    });
  }

  setRemoteMuted(muted: boolean): void {
    if (this.remoteAudio) {
      this.remoteAudio.muted = muted;
    }
  }

  flushInputAudioBuffer(): void {
    this.send({ type: "input_audio_buffer.clear" });
  }

  /** server_vad — manual = escucha sin create_response; auto = conversación fluida. */
  private applyTurnDetection(mode: "off" | "listen" | "manual" | "auto"): void {
    if (!this.dc || this.dc.readyState !== "open") return;
    const turn_detection =
      mode === "off"
        ? null
        : {
            type: "server_vad" as const,
            threshold: CedLiveClient.SERVER_VAD.threshold,
            prefix_padding_ms: CedLiveClient.SERVER_VAD.prefix_padding_ms,
            silence_duration_ms: CedLiveClient.SERVER_VAD.silence_duration_ms,
            create_response: mode === "auto",
            // FitLine (voz económica): eco del altavoz no debe cortar a CED.
            interrupt_response:
              this.voiceProfile === "fitline"
                ? false
                : CedLiveClient.SERVER_VAD.interrupt_response,
          };
    this.send({
      type: "session.update",
      session: {
        type: "realtime",
        audio: {
          input: {
            turn_detection,
          },
        },
      },
    });
  }

  private setServerAutoResponse(enabled: boolean): void {
    this.applyTurnDetection(enabled ? "auto" : "manual");
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.triggerBargeIn();
    this.applyTurnDetection("off");
    this.userMicLive = false;
    this.sessionReady = false;
    this.sendBlocked = true;
    this.greetingSent = false;
    this.greetingInFlight = false;
    this.greetingComplete = false;
    this.heardUserSinceGreeting = false;
    this.greetingGraceUntil = 0;
    this.awaitingFirstUserSpeech = false;
    this.clearUserResponseTimer();
    this.intentionalResponse = false;
    this.intentionalResponseActive = false;
    this.blockAutoResponsesUntil = 0;
    this.singleSpeechSlot = "closed";
    this.lastMeaningfulUserUtterance = "";
    this.advancedBriefInFlight = false;
    this.lastGreetingPhrase = "";
    this.lastCompletedModelUtterance = "";
    this.lastModelSpeechAt = 0;
    this.exactPhraseExpected = "";
    this.greetingCompletedAt = 0;
    this.userTurnResponded = false;
    this.lastArmedTranscript = "";
    this.turnCooldownUntil = 0;
    this.userTurnScheduled = false;
    this.lastResponseCreateAt = 0;
    this.userResponseArmed = false;
    this.postGreetingLockUntil = 0;
    this.serverConversationMode = false;
    this.waitingForFirstUserInput = false;
    this.pendingEnableAutoAfterResponse = false;
    this.connectGen += 1;

    this.dc?.close();
    this.dc = null;

    this.detachCameraStream();
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }

    if (this.remoteAudio) {
      this.remoteAudio.muted = true;
      this.remoteAudio.srcObject = null;
      this.remoteAudio = null;
    }

    voiceTelemetry.setWsState("disconnected");
    voiceTelemetry.setSessionId(null);
  }

  isCameraAttached(): boolean {
    return Boolean(this.videoSender && this.videoStream);
  }

  /** Agrega track de video al peer WebRTC (visión nativa Realtime). */
  async attachCameraStream(stream: MediaStream): Promise<boolean> {
    if (!this.pc || !stream.getVideoTracks().length) return false;
    const track = stream.getVideoTracks()[0];
    if (!track) return false;
    if ("contentHint" in track) {
      track.contentHint = "detail";
    }
    try {
      if (this.videoSender) {
        await this.videoSender.replaceTrack(track);
      } else {
        this.videoSender = this.pc.addTrack(track, stream);
      }
      this.videoStream = stream;
      this.notifyCameraContext(true);
      cedVoiceLog(5, "WebRTC video track attached");
      return true;
    } catch (err) {
      cedVoiceError("attachCameraStream failed", err);
      return false;
    }
  }

  /** Quita el track de video del peer WebRTC. */
  detachCameraStream(): void {
    const hadVideo = Boolean(this.videoSender);
    if (this.videoSender && this.pc) {
      try {
        this.pc.removeTrack(this.videoSender);
      } catch {
        /* ignore */
      }
    }
    this.videoSender = null;
    this.videoStream = null;
    if (hadVideo) {
      this.notifyCameraContext(false);
    }
  }

  private notifyCameraContext(active: boolean): void {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    const text = active
      ? "[CED sistema] Cámara ACTIVA. Para describir algo visual invoca analyze_camera_frame o buscar_lo_visible. " +
        "PROHIBIDO afirmar que ves sin invocar herramienta."
      : "[CED sistema] Cámara DESACTIVADA. PROHIBIDO decir que ves algo, al usuario o su entorno. " +
        "Si piden visión, invoca request_camera_activation.";
    this.send({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    });
  }

  async connect(
    handlers: CedLiveHandlers,
    options: CedLiveConnectOptions,
  ): Promise<boolean> {
    if (this.connectInFlight) return false;
    if (!options.micStream?.getAudioTracks().length) {
      handlers.onError?.("Micrófono no disponible para WebRTC.");
      return false;
    }

    this.connectInFlight = true;
    this.handlers = handlers;
    this.voiceProfile = options.voiceProfile ?? "jarvis";
    this.sendBlocked = true;
    this.disconnect();
    this.intentionalClose = false;
    this.micStream = options.micStream;
    this.userTranscriptAcc = "";
    this.modelTranscriptAcc = "";
    this.processedCallIds.clear();
    this.recentToolAt.clear();
    this.activeResponseId = null;
    this.responseInProgress = false;
    this.clearUserResponseTimer();
    this.intentionalResponse = false;
    this.userTurnResponded = false;
    this.lastArmedTranscript = "";
    this.turnCooldownUntil = 0;
    this.userTurnScheduled = false;
    this.lastResponseCreateAt = 0;

    const generation = this.connectGen;
    const isStale = () => generation !== this.connectGen;

    handlers.onState?.("connecting");
    voiceTelemetry.reset();
    voiceTelemetry.setWsState("connecting");
    voiceTelemetry.setSessionId(`openai-webrtc-${Date.now()}`);

    const tokenRes = await fetchEphemeralTokenCached(options.voiceName, {
      language: options.language,
      responseSpeed: options.responseSpeed,
      voicePace: options.voicePace,
      voiceWarmth: options.voiceWarmth,
      voiceEnergy: options.voiceEnergy,
      voiceProfile: options.voiceProfile,
    });
    if (isStale()) {
      this.connectInFlight = false;
      return false;
    }
    if (!tokenRes.ok) {
      handlers.onState?.("error");
      handlers.onError?.(tokenRes.error);
      voiceTelemetry.setWsState("error", tokenRes.error);
      this.connectInFlight = false;
      return false;
    }

    const voiceName = tokenRes.voiceName ?? "alloy";
    this.model = tokenRes.model;
    this.userAddress = tokenRes.userAddress ?? null;
    this.toolsEnabled = tokenRes.toolsEnabled !== false;
    if (!this.toolsEnabled) {
      cedVoiceError(
        "[REALTIME] Sesión SIN herramientas — publicar/imagen/búsqueda vía tools no funcionarán. Revisa logs API.",
      );
    }
    cedRealtimeLog("session.connect", {
      model: this.model,
      toolsEnabled: this.toolsEnabled,
      toolsCount: tokenRes.toolsCount ?? null,
      sessionVia: tokenRes.sessionVia ?? null,
    });
    voiceTelemetry.setActiveVoice(voiceName);

    try {
      const pc = new RTCPeerConnection();
      this.pc = pc;

      const remoteAudio = document.createElement("audio");
      remoteAudio.autoplay = true;
      remoteAudio.setAttribute("playsinline", "true");
      remoteAudio.preload = "auto";
      remoteAudio.volume = 1;
      this.remoteAudio = remoteAudio;

      pc.ontrack = (ev) => {
        const [stream] = ev.streams;
        if (stream && this.remoteAudio) {
          this.remoteAudio.srcObject = stream;
          void this.remoteAudio.play().catch(() => undefined);
          stream.getAudioTracks().forEach((track) => {
            cedRealtimeLog("audio.track", {
              label: track.label,
              enabled: track.enabled,
              muted: track.muted,
              readyState: track.readyState,
            });
          });
        }
      };

      pc.onconnectionstatechange = () => {
        if (isStale() || !this.pc) return;
        const state = this.pc.connectionState;
        cedVoiceLog(5, "WebRTC connection state", { state });
        if (state === "failed") {
          this.sessionReady = false;
          this.sendBlocked = true;
          handlers.onState?.("error");
          handlers.onError?.("Conexión WebRTC falló.");
          voiceTelemetry.setWsState("error", "webrtc failed");
          handlers.onClose?.(classifyPeerClose(true));
        }
        if (state === "disconnected" || state === "closed") {
          if (!this.intentionalClose) {
            this.sessionReady = false;
            this.sendBlocked = true;
            voiceTelemetry.setWsState("closed");
            handlers.onState?.("closed");
            handlers.onClose?.(classifyPeerClose(true));
          }
        }
      };

      options.micStream.getAudioTracks().forEach((track) => {
        pc.addTrack(track, options.micStream);
      });

      const dc = pc.createDataChannel("oai-events");
      this.dc = dc;

      const readyPromise = new Promise<boolean>((resolve) => {
        const readyTimeout = window.setTimeout(() => {
          if (!this.sessionReady && !isStale()) {
            handlers.onError?.("OpenAI no respondió a tiempo (WebRTC).");
            handlers.onState?.("error");
            resolve(false);
          }
        }, 20000);

        const markReady = () => {
          if (this.sessionReady || isStale()) return;
          window.clearTimeout(readyTimeout);
          this.sessionReady = true;
          this.sendBlocked = false;
          this.setServerAutoResponse(false);
          this.applyTurnDetection("off");
          this.flushInputAudioBuffer();
          voiceTelemetry.markSetupComplete();
          handlers.onState?.("connected");
          handlers.onSessionReady?.();
          cedVoiceLog(6, "OpenAI WebRTC session ready");
          this.connectInFlight = false;
          resolve(true);
        };

        dc.onopen = () => {
          cedVoiceLog(5, "WebRTC data channel open");
        };

        dc.onmessage = (ev) => {
          if (isStale()) return;
          try {
            const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
            void this.handleServerEvent(msg, markReady);
          } catch {
            /* ignore */
          }
        };

        dc.onclose = () => {
          if (!this.intentionalClose && !isStale()) {
            this.sessionReady = false;
            this.sendBlocked = true;
            voiceTelemetry.setWsState("closed");
            handlers.onState?.("closed");
            handlers.onClose?.(classifyPeerClose(true));
          }
        };
      });

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const negotiate = await negotiateRealtimeCall(
        offer.sdp ?? "",
        tokenRes.clientSecret,
      );
      if (isStale()) {
        this.connectInFlight = false;
        return false;
      }
      if (!negotiate.ok) {
        handlers.onState?.("error");
        handlers.onError?.(negotiate.error);
        voiceTelemetry.setWsState("error", negotiate.error);
        this.connectInFlight = false;
        return false;
      }

      await pc.setRemoteDescription({
        type: "answer",
        sdp: negotiate.sdpAnswer,
      });

      voiceTelemetry.setWsState("connected");
      cedVoiceLog(5, "WebRTC negociado", { model: this.model, voice: voiceName });

      return await readyPromise;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error WebRTC";
      cedVoiceError("[OPENAI:WebRTC]", msg);
      handlers.onState?.("error");
      handlers.onError?.(msg);
      voiceTelemetry.setWsState("error", msg);
      this.connectInFlight = false;
      return false;
    }
  }

  private async handleServerEvent(
    msg: Record<string, unknown>,
    markReady: () => void,
  ): Promise<void> {
    const handlers = this.handlers;
    const type = String(msg.type ?? "");

    cedRealtimeLog("event", { type });

    if (type === "session.created") {
      const session = msg.session as { tools?: unknown[] } | undefined;
      const toolsCount = session?.tools?.length ?? 0;
      if (toolsCount > 0) this.toolsEnabled = true;
      cedRealtimeLog("session.ready", { type, toolsCount, toolsEnabled: this.toolsEnabled });
      markReady();
      return;
    }

    if (type === "session.updated") {
      const session = msg.session as { tools?: unknown[] } | undefined;
      const toolsCount = session?.tools?.length ?? 0;
      if (toolsCount > 0) this.toolsEnabled = true;
      cedRealtimeLog("session.updated", { toolsCount, toolsEnabled: this.toolsEnabled });
      return;
    }

    if (type === "response.function_call_arguments.delta") {
      cedRealtimeLog("tool.args.delta", { delta: String(msg.delta ?? "").slice(0, 120) });
      return;
    }

    if (type === "response.output_item.done") {
      const item = msg.item as
        | { type?: string; name?: string; call_id?: string; arguments?: string }
        | undefined;
      if (item?.type === "function_call" && item.call_id && item.name) {
        cedRealtimeLog("tool.output_item.done", {
          name: item.name,
          call_id: item.call_id,
        });
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(String(item.arguments ?? "{}")) as Record<string, unknown>;
        } catch {
          args = {};
        }
        await this.dispatchTool(item.name, item.call_id, args);
      }
      return;
    }

    if (type === "response.created") {
      const response = msg.response as { id?: string } | undefined;
      if (!this.allowResponseCreated(response?.id)) {
        return;
      }
      this.activeResponseId = response?.id ?? null;
      this.responseInProgress = true;
      handlers.onResponseStart?.();
      return;
    }

    if (isResponseAudioTranscriptDelta(type)) {
      const delta = String(msg.delta ?? "");
      this.modelTranscriptAcc += delta;
      if (
        this.outboundLocked &&
        this.exactPhraseExpected &&
        this.modelTranscriptAcc.trim().length >= 12 &&
        this.spokenMatchesExactPhrase(this.exactPhraseExpected, this.modelTranscriptAcc)
      ) {
        this.exactPhraseHadUsableAudio = true;
      }
      const leak = this.isPromptInstructionLeak(this.modelTranscriptAcc);
      const exactMismatch =
        this.outboundLocked &&
        this.exactPhraseExpected.length >= 10 &&
        this.modelTranscriptAcc.trim().length >= 28 &&
        !this.spokenMatchesExactPhrase(this.exactPhraseExpected, this.modelTranscriptAcc) &&
        /mercader|importar|cat[aá]logo|producto de mercader|necesitas importar|qu[eé] producto|<<<|>>>|\bmire[,.]?\s+\w+/i.test(
          this.modelTranscriptAcc,
        );
      if (
        leak ||
        exactMismatch ||
        (!this.outboundLocked && this.isRogueModelGreeting(this.modelTranscriptAcc))
      ) {
        cedRealtimeLog(
          leak ? "response.prompt_leak" : exactMismatch ? "response.exact_mismatch" : "response.rogue_greeting",
          {
            text: this.modelTranscriptAcc.slice(0, 100),
          },
        );
        if ((leak || exactMismatch) && this.outboundLocked) this.exactPhraseLeak = true;
        this.triggerBargeIn();
        this.modelTranscriptAcc = "";
        this.userResponseArmed = false;
        this.intentionalResponseActive = false;
        return;
      }
      if (delta) handlers.onTranscriptUpdate?.(this.modelTranscriptAcc, "model");
      return;
    }

    if (isResponseAudioDone(type)) {
      handlers.onModelAudioDone?.();
      this.modelAudioDoneResolve?.();
      this.modelAudioDoneResolve = null;
      return;
    }

    if (isInputTranscriptionCompleted(type)) {
      const transcript = String(msg.transcript ?? "").trim();
      if (!transcript || /^<noise>$/i.test(transcript)) return;

      // Filtrar eco/ruido ANTES de UI/chat — si no, el saludo aparece como «Usted».
      if (
        this.isLikelyBackgroundNoise(transcript) ||
        this.isLikelyAmbientOrEcho(transcript) ||
        this.isEchoOfCedGreeting(transcript) ||
        this.isEchoOfOwnSpeech(transcript) ||
        this.isSocialFillerSpeech(transcript)
      ) {
        cedRealtimeLog("transcript.noise", { transcript: transcript.slice(0, 80) });
        this.userTranscriptAcc = "";
        this.flushInputAudioBuffer();
        return;
      }

      // Con respuesta en curso, STT residual ≈ eco (mic suele estar muteado).
      if (this.responseInProgress || this.outboundLocked || this.greetingInFlight) {
        cedRealtimeLog("transcript.ignored_during_response", {
          transcript: transcript.slice(0, 80),
        });
        this.userTranscriptAcc = "";
        this.flushInputAudioBuffer();
        return;
      }

      // Tras saludo: hola/cómo estás NO desbloquean ni van al chat.
      const casualPhrase = this.phraseForCasualSocial(transcript);
      if (
        casualPhrase &&
        this.greetingComplete &&
        (this.waitingForFirstUserInput || this.awaitingFirstUserSpeech)
      ) {
        cedRealtimeLog("transcript.casual_ignored_awaiting_real", {
          transcript: transcript.slice(0, 60),
        });
        this.userTranscriptAcc = "";
        this.flushInputAudioBuffer();
        return;
      }

      if (!this.isMeaningfulUserSpeech(transcript)) {
        this.userTranscriptAcc = "";
        this.flushInputAudioBuffer();
        return;
      }

      handlers.onTranscriptUpdate?.(transcript, "user");
      this.userTranscriptAcc = transcript;

      this.markUserSpeechHeard(transcript);
      if (casualPhrase && this.greetingComplete) {
        void this.handleCasualSocialTurn(casualPhrase);
        return;
      }
      const firstTurn = this.onFirstUserTranscript(transcript);
      const intent = parseCameraIntent(transcript);
      if (intent === "deactivate" && this.userMicLive) {
        handlers.onCameraIntent?.(intent);
      } else if (intent === "activate" && this.userMicLive) {
        handlers.onCameraIntent?.(intent);
      }
      // Un solo create por turno — firstTurn ya armó; no resetear userTurnResponded.
      if (
        this.greetingComplete &&
        !this.outboundLocked &&
        this.userMicLive &&
        !this.responseInProgress &&
        (firstTurn || !this.userTurnResponded)
      ) {
        this.triggerUserResponse();
      }
      return;
    }

    if (type === "input_audio_buffer.speech_stopped") {
      handlers.onSpeechStopped?.();
      if (
        this.greetingComplete &&
        this.userMicLive &&
        this.heardUserSinceGreeting &&
        this.lastMeaningfulUserUtterance &&
        !this.responseInProgress &&
        !this.userTurnResponded
      ) {
        this.triggerUserResponse();
      }
      return;
    }

    if (type === "response.cancelled") {
      this.activeResponseId = null;
      this.responseInProgress = false;
      this.intentionalResponse = false;
      this.intentionalResponseActive = false;
      this.userResponseArmed = false;
      // Permitir reintento inmediato — si no, queda “pegado” tras un cancel.
      this.userTurnResponded = false;
      this.flushInputAudioBuffer();
      handlers.onInterrupted?.();
      return;
    }

    if (type === "input_audio_buffer.speech_started") {
      if (this.greetingComplete && !this.responseInProgress) {
        this.userTurnResponded = false;
        this.lastArmedTranscript = "";
      }
      return;
    }

    if (type === "response.done") {
      const response = msg.response as
        | { status?: string; status_details?: unknown }
        | undefined;
      if (response?.status === "cancelled") {
        cedVoiceLog(5, "OpenAI response cancelled");
      }
      if (response?.status === "failed") {
        cedVoiceError("[REALTIME] response.failed", response.status_details);
      }
      cedRealtimeLog("response.done", {
        status: response?.status ?? "unknown",
      });
      this.activeResponseId = null;
      this.responseInProgress = false;
      this.intentionalResponse = false;
      this.intentionalResponseActive = false;
      this.advancedBriefInFlight = false;
      this.userTurnScheduled = false;
      this.userResponseArmed = false;
      if (this.pendingEnableAutoAfterResponse && this.serverConversationMode) {
        this.pendingEnableAutoAfterResponse = false;
        this.applyTurnDetection("auto");
        cedRealtimeLog("turn_detection.auto_after_response_done", {});
      }
      if (this.modelTranscriptAcc.trim()) {
        const modelText = this.modelTranscriptAcc.trim();
        this.lastCompletedModelUtterance = modelText;
        this.lastModelSpeechAt = Date.now();
        if (!this.isRogueModelGreeting(modelText)) {
          handlers.onTranscript?.(modelText, "model");
        } else {
          cedRealtimeLog("transcript.rogue_model_skipped", { text: modelText.slice(0, 80) });
        }
        this.modelTranscriptAcc = "";
      }
      if (this.userTranscriptAcc.trim()) {
        const userText = this.userTranscriptAcc.trim();
        if (
          !this.isLikelyBackgroundNoise(userText) &&
          !this.isLikelyAmbientOrEcho(userText) &&
          !this.isEchoOfCedGreeting(userText) &&
          !this.isEchoOfOwnSpeech(userText) &&
          !this.isSocialFillerSpeech(userText) &&
          this.isMeaningfulUserSpeech(userText)
        ) {
          handlers.onTranscript?.(userText, "user");
        }
        this.userTranscriptAcc = "";
      }
      voiceTelemetry.markTurnComplete();
      handlers.onTurnComplete?.();
      return;
    }

    if (type === "response.function_call_arguments.done") {
      const callId = String(msg.call_id ?? "");
      const name = String(msg.name ?? "");
      cedRealtimeLog("tool.args.done", {
        name,
        call_id: callId,
        arguments: String(msg.arguments ?? "").slice(0, 240),
      });
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(String(msg.arguments ?? "{}")) as Record<string, unknown>;
      } catch {
        args = {};
      }
      await this.dispatchTool(name, callId, args);
      return;
    }

    if (type === "error") {
      const err = msg.error as { message?: string; code?: string } | undefined;
      const message = err?.message ?? "Realtime error";
      if (isBenignRealtimeError(message)) {
        cedVoiceLog(5, "OpenAI benign error ignored", { message });
        // Si el server rechazó un create duplicado, no dejar el cliente trabado.
        if (
          /active response in progress|already has an active response|wait until the response is finished/i.test(
            message,
          )
        ) {
          // Mantener responseInProgress=true hasta response.done real; solo limpiar flags de armado.
          this.userResponseArmed = false;
          this.intentionalResponse = false;
          this.intentionalResponseActive = false;
        } else if (/no active response|cancellation failed|response_cancel/i.test(message)) {
          this.activeResponseId = null;
          this.responseInProgress = false;
        }
        return;
      }
      voiceTelemetry.setWsState("error", message);
      handlers.onError?.(message);
    }
  }

  sendVideoJpeg(base64Jpeg: string): void {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    const now = Date.now();
    if (now - this.lastVideoFrameAt < CedLiveClient.VIDEO_FRAME_MIN_MS) return;
    const trimmed = base64Jpeg.trim();
    if (!trimmed) return;
    this.lastVideoFrameAt = now;
    const url = trimmed.startsWith("data:")
      ? trimmed
      : `data:image/jpeg;base64,${trimmed}`;
    this.send({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_image", image_url: url }],
      },
    });
  }

  sendAdvancedSystemAck(): void {
    if (this.isGreetingInProgress()) return;
    void this.enqueueControlledBrief(CED_VOICE_PROFILE_LOCK.advancedSystem.ackInstruction);
  }

  setUserAddress(address: UserAddressContext | null): void {
    this.userAddress = address;
  }

  getUserAddress(): UserAddressContext | null {
    return this.userAddress;
  }

  isAwaitingFirstUserSpeech(): boolean {
    return this.awaitingFirstUserSpeech;
  }

  sendSessionGreeting(): void {
    if (
      this.greetingSent ||
      this.greetingInFlight ||
      !this.dc ||
      !this.sessionReady ||
      this.sendBlocked
    ) {
      return;
    }
    this.greetingSent = true;
    this.greetingInFlight = true;
    void (async () => {
      try {
        this.applyTurnDetection("off");
        this.setMicTrackEnabled(false);
        this.flushInputAudioBuffer();
        const phrase = cedReceptionGreetingPhrase(this.voiceProfile, this.userAddress);
        this.lastGreetingPhrase = phrase;
        if (this.responseInProgress) {
          this.triggerBargeIn();
          await this.waitForResponseIdle(1200);
        }
        this.blockAutoResponsesUntil = Date.now() + 4_000;
        this.postGreetingLockUntil = 0;
        this.beginSingleSpeechSlot();
        cedRealtimeLog("greeting.create", { phrase });
        this.exactPhraseLeak = false;
        this.exactPhraseHadUsableAudio = false;
        await this.speakExactPhrase(phrase, 80);
        // Solo reintentar si el 1er intento falló SIN audio usable — nunca apilar 2 versiones.
        if (
          this.exactPhraseLeak &&
          !this.exactPhraseHadUsableAudio &&
          !this.sendBlocked
        ) {
          cedRealtimeLog("greeting.retry_after_leak", { phrase });
          this.exactPhraseLeak = false;
          await this.sleep(350);
          await this.speakExactPhrase(phrase, 64);
        }
        this.flushInputAudioBuffer();
        this.endSingleSpeechSlot();
        // Ventana corta solo para eco del propio saludo; enableListeningAfterGreeting la limpia.
        this.greetingGraceUntil = Date.now() + 2_000;
        this.greetingComplete = true;
        this.greetingCompletedAt = Date.now();
        this.awaitingFirstUserSpeech = true;
        this.heardUserSinceGreeting = false;
        this.lastMeaningfulUserUtterance = "";
        this.turnCooldownUntil = 0;
        this.handlers.onGreetingComplete?.();
      } finally {
        this.greetingInFlight = false;
      }
    })();
  }

  /** Una sola frase exacta — fuera del historial de conversación. */
  private async speakExactPhrase(phrase: string, maxOutputTokens = 80): Promise<void> {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    const line = phrase.trim();
    if (!line) return;
    this.outboundLocked = true;
    this.setServerAutoResponse(false);
    this.beginSingleSpeechSlot();
    this.exactPhraseLeak = false;
    this.exactPhraseHadUsableAudio = false;
    this.exactPhraseExpected = line;
    this.modelTranscriptAcc = "";
    try {
      this.intentionalResponse = true;
      this.intentionalResponseActive = true;
      // Sin <<<>>>: el mini las leía en voz alta y apilaba variantes.
      this.send({
        type: "response.create",
        response: {
          conversation: "none",
          max_output_tokens: maxOutputTokens,
          tool_choice: "none",
          instructions: [
            "Eres un lector TTS. Emite UNA sola frase de audio.",
            "Di palabra por palabra SOLO esta línea (sin comillas, sin prefijos, sin nombres inventados):",
            line,
            "PROHIBIDO: añadir texto, saludar extra, Claroclaro, Mire Nombre, inglés, o una segunda versión.",
            "Si ya dijiste la línea, DETENTE. No generes otra variante.",
          ].join("\n"),
        },
      });
      const idleMs = Math.min(25_000, 8_000 + maxOutputTokens * 40);
      const audioMs = Math.min(22_000, 6_000 + maxOutputTokens * 36);
      await this.waitForResponseIdle(idleMs);
      await this.waitForModelAudioDone(audioMs);
      await this.sleep(400);
      const spoken = this.modelTranscriptAcc.trim() || this.lastCompletedModelUtterance;
      if (spoken && /<<<|>>>|\bmire[,.]?\s+\w+/i.test(spoken)) {
        this.exactPhraseLeak = true;
        this.triggerBargeIn();
      } else if (spoken && !this.spokenMatchesExactPhrase(line, spoken)) {
        cedRealtimeLog("exact_phrase.mismatch", {
          expected: line.slice(0, 80),
          spoken: spoken.slice(0, 80),
        });
        // Si ya hubo audio usable, no marcar leak (reintento apilaría otra versión).
        if (!this.exactPhraseHadUsableAudio) {
          this.exactPhraseLeak = true;
          this.triggerBargeIn();
        }
      } else if (spoken && this.spokenMatchesExactPhrase(line, spoken)) {
        this.exactPhraseHadUsableAudio = true;
      }
      this.flushInputAudioBuffer();
    } finally {
      this.outboundLocked = false;
      this.exactPhraseExpected = "";
      this.intentionalResponse = false;
      this.intentionalResponseActive = false;
      this.endSingleSpeechSlot();
    }
  }

  /** Lectura exacta para resultados largos (comentarios, prospección). */
  speakExactNarrationAsync(phrase: string): Promise<void> {
    const text = phrase.trim();
    if (!text || this.isGreetingInProgress()) return Promise.resolve();
    const maxOutputTokens = Math.min(720, Math.max(150, Math.ceil(text.length / 1.4) + 72));
    return this.speakExactPhrase(text, maxOutputTokens);
  }

  private waitForModelAudioDone(maxMs = 8000): Promise<void> {
    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => {
        this.modelAudioDoneResolve = null;
        resolve();
      }, maxMs);
      this.modelAudioDoneResolve = () => {
        window.clearTimeout(timeout);
        resolve();
      };
    });
  }

  /** Presencia tras silencio — una frase exacta. */
  sendPresenceBrief(phrase: string): void {
    const text = phrase.trim();
    if (!text || this.greetingInFlight) return;
    void (async () => {
      await this.speakExactPhrase(text, 60);
    })();
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private enqueueControlledBrief(
    turnText: string,
    maxOutputTokens = 400,
  ): Promise<void> {
    const task = async () => {
      await this.sendControlledBrief(turnText, maxOutputTokens);
    };
    this.briefChain = this.briefChain.then(task, task);
    return this.briefChain;
  }

  private async sendControlledBrief(
    turnText: string,
    maxOutputTokens = 400,
  ): Promise<void> {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    this.outboundLocked = true;
    this.advancedBriefInFlight = maxOutputTokens > 400;
    this.blockAutoResponsesUntil = Date.now() + Math.max(12000, maxOutputTokens * 40);
    this.beginSingleSpeechSlot();
    try {
      if (this.responseInProgress) {
        this.triggerBargeIn();
        await this.waitForResponseIdle();
      }
      this.setServerAutoResponse(false);
      this.send({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text: turnText }],
        },
      });
      this.intentionalResponse = true;
      this.intentionalResponseActive = true;
      this.send({
        type: "response.create",
        response: {
          max_output_tokens: maxOutputTokens,
          tool_choice: "none",
        },
      });
      this.lastResponseCreateAt = Date.now();
      const idleMs = maxOutputTokens > 400 ? 48000 : 18000;
      await this.waitForResponseIdle(idleMs);
      await this.waitForModelAudioDone(12000);
      await this.sleep(400);
      this.flushInputAudioBuffer();
      this.turnCooldownUntil = Date.now() + 1200;
    } finally {
      this.outboundLocked = false;
      this.advancedBriefInFlight = false;
      this.intentionalResponse = false;
      this.intentionalResponseActive = false;
      this.blockAutoResponsesUntil = Date.now() + 800;
      this.endSingleSpeechSlot();
    }
  }

  /** Narración controlada — esperar a que termine (p. ej. comentarios Instagram). */
  sendNarrationBriefAsync(summary: string): Promise<void> {
    const text = summary.trim();
    if (!text || this.isGreetingInProgress()) return Promise.resolve();
    const tokens = Math.min(900, Math.max(160, Math.ceil(text.length / 2.4)));
    return this.enqueueControlledBrief(cedBriefTurn(text), tokens);
  }

  sendNarrationBrief(summary: string): void {
    const text = summary.trim();
    if (!text || this.isGreetingInProgress()) return;
    void this.enqueueControlledBrief(cedBriefTurn(text));
  }

  sendPublishConfirm(platform: "facebook" | "instagram"): void {
    if (this.isGreetingInProgress()) return;
    void this.enqueueControlledBrief(cedPublishConfirmTurn(platform));
  }

  sendWebSearchAck(): void {
    /* Obsoleto — provocaba doble respuesta (ack + brief). Usar solo sendNarrationBrief. */
  }

  triggerBargeIn(): void {
    if (!this.responseInProgress) return;
    const cancel: Record<string, unknown> = { type: "response.cancel" };
    if (this.activeResponseId) cancel.response_id = this.activeResponseId;
    this.send(cancel);
  }

  private waitForResponseIdle(maxMs = CedLiveClient.RESPONSE_IDLE_MS): Promise<void> {
    if (!this.responseInProgress) return Promise.resolve();
    return new Promise((resolve) => {
      const start = performance.now();
      const tick = () => {
        if (!this.responseInProgress || performance.now() - start > maxMs) {
          if (this.responseInProgress && performance.now() - start > maxMs) {
            this.forceReleaseTurn();
          }
          resolve();
          return;
        }
        setTimeout(tick, 40);
      };
      tick();
    });
  }

  private async sendClientTurn(text: string): Promise<void> {
    if (!this.dc || !this.sessionReady || this.sendBlocked) return;
    if (this.responseInProgress) {
      cedVoiceLog(5, "Cancelando respuesta previa antes de nuevo turno CED");
      this.triggerBargeIn();
      await this.waitForResponseIdle();
    }
    try {
      this.send({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text }],
        },
      });
      this.send({ type: "response.create" });
    } catch (err) {
      cedVoiceError("sendClientTurn failed", err);
    }
  }

  private send(payload: Record<string, unknown>): void {
    if (!this.dc || this.dc.readyState !== "open") return;
    this.dc.send(JSON.stringify(payload));
  }

  private dispatchVoiceToolResult(
    toolName: string,
    result: Record<string, unknown>,
  ): void {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent("ced-voice-tool-result", {
        detail: { tool_name: toolName, result },
      }),
    );
  }

  private async dispatchTool(
    rawName: string,
    callId: string,
    args: Record<string, unknown>,
  ): Promise<void> {
    if (!callId) {
      cedRealtimeLog("tool.skip", { reason: "missing call_id", name: rawName });
      return;
    }
    if (this.processedCallIds.has(callId)) {
      cedRealtimeLog("tool.skip", { reason: "duplicate call_id", call_id: callId, name: rawName });
      return;
    }
    const dedupeKey = `${rawName}:${JSON.stringify(args)}`;
    const lastAt = this.recentToolAt.get(dedupeKey) ?? 0;
    if (Date.now() - lastAt < CedLiveClient.TOOL_COOLDOWN_MS) {
      cedRealtimeLog("tool.skip", { reason: "cooldown", name: rawName, dedupeKey });
      return;
    }
    this.recentToolAt.set(dedupeKey, Date.now());
    this.processedCallIds.add(callId);

    const h = this.handlers;
    const normalized = normalizeToolInvocation(rawName, args);
    const name = normalized.name;
    args = normalized.args;
    cedRealtimeLog("tool.execute", { name: rawName, resolved: name, call_id: callId, args });

    try {
      if (rawName === "search_web") {
        const query = String(args.query ?? "").trim();
        h.onToolStart?.("search_web");
        const brief = await fetchVoiceBrief(query || "noticias hoy", "news");
        const spoken = brief.ok ? brief.summary : "No pude buscar en internet.";
        await this.submitToolOutput(callId, { status: "ok", spoken });
        return;
      }

      if (rawName === "request_camera_activation") {
        if (!this.userExplicitlyRequestedVision()) {
          cedRealtimeLog("tool.camera.blocked", { last: this.lastMeaningfulUserUtterance.slice(0, 60) });
          await this.submitToolOutput(callId, { status: "ignored", silent: true });
          return;
        }
        h.onToolStart?.("request_camera_activation");
        const ok = (await h.onCameraTool?.("activate")) ?? false;
        await this.submitToolOutput(callId, {
          status: ok ? "ok" : "error",
          spoken: ok
            ? "Cámara activa."
            : "No pude activar la cámara. Revisa permisos del navegador.",
        });
        return;
      }

      if (rawName === "request_camera_deactivation") {
        h.onToolStart?.("request_camera_deactivation");
        await h.onCameraTool?.("deactivate");
        await this.submitToolOutput(callId, {
          status: "ok",
          spoken: "Cámara apagada.",
        });
        return;
      }

      if (rawName === "generate_image") {
        const last = this.lastMeaningfulUserUtterance.toLowerCase();
        if (
          !/\b(imagen|foto|genera|crea|dibuja|ilustr|picture|image)\b/i.test(last)
        ) {
          cedRealtimeLog("tool.image.blocked", { last: last.slice(0, 60) });
          await this.submitToolOutput(callId, { status: "ignored", silent: true });
          return;
        }
        const prompt = String(args.prompt ?? "").trim();
        const quality = String(args.quality ?? "auto");
        h.onToolStart?.("generate_image");
        const result = await fetchGenerateImage(
          prompt || "imagen creativa",
          quality as "auto" | "standard" | "hd",
        );
        if (result.ok) {
          h.onGeneratedImage?.(result.url, prompt);
          const hTitle = this.userAddress?.honorific?.trim() || "Señor";
          const toolResult = {
            status: "ok",
            spoken: `Imagen generada, ${hTitle}.`,
            image_url: result.url,
            prompt,
          };
          this.dispatchVoiceToolResult("generate_image", toolResult);
          await this.submitToolOutput(callId, toolResult);
        } else {
          const toolResult = {
            status: "error",
            spoken: result.error || "No pude generar la imagen.",
          };
          this.dispatchVoiceToolResult("generate_image", toolResult);
          await this.submitToolOutput(callId, toolResult);
        }
        return;
      }

      if (rawName === "generate_image_with_reference") {
        const last = this.lastMeaningfulUserUtterance.toLowerCase();
        if (
          !/\b(imagen|foto|variaci|genera|crea|cámara|camara|referencia|parecido|estilo)\b/i.test(
            last,
          )
        ) {
          cedRealtimeLog("tool.image_ref.blocked", { last: last.slice(0, 60) });
          await this.submitToolOutput(callId, { status: "ignored", silent: true });
          return;
        }
        h.onToolStart?.("generate_image_with_reference");
        if (h.onGenerateImageWithReference) {
          const result = await h.onGenerateImageWithReference(args);
          if (result.ok && result.url) {
            h.onGeneratedImage?.(result.url, String(args.prompt ?? ""));
            await this.submitToolOutput(callId, {
              status: "ok",
              spoken: result.spoken || "Ahí está.",
              image_url: result.url,
            });
          } else {
            await this.submitToolOutput(callId, {
              status: "error",
              spoken: result.error || result.spoken || "No pude generar con la referencia.",
            });
          }
        } else {
          await this.submitToolOutput(callId, {
            status: "error",
            spoken: "No tengo acceso a la imagen de referencia. Muéstrame o adjunta una imagen primero.",
          });
        }
        return;
      }

      if (name === CONSULTAR_SISTEMA_AVANZADO) {
        const prompt = String(args.prompt ?? args.query ?? "").trim();
        const allowed = h.shouldAllowAdvancedTool?.(prompt) ?? false;
        if (!allowed) {
          h.onAdvancedToolBlocked?.(prompt);
          if (this.responseInProgress) {
            this.triggerBargeIn();
            await this.waitForResponseIdle(1600);
          }
          await this.speakExactPhrase(CED_ADVANCED_CONFIRM_PHRASE, 36);
          await this.submitToolOutput(callId, {
            status: "needs_confirmation",
            prompt,
            silent: true,
          });
          return;
        }
        h.onToolStart?.(name);
        if (this.responseInProgress) {
          this.triggerBargeIn();
          await this.waitForResponseIdle(2400);
        }
        await this.speakExactPhrase(`Un momento, ${this.resolveHonorific()}.`, 32);
        const result = await fetchDeepAnalysis(
          prompt || "consulta general",
          CED_VOICE_PROFILE_LOCK.advancedSystem.fetchTimeoutMs,
        );
        const spoken = result.ok ? result.result : "No pude completar el análisis.";
        await this.submitToolOutput(callId, {
          status: result.ok ? "ok" : "error",
          spoken,
          briefOnly: true,
          advancedBrief: true,
        });
        return;
      }

      if (name === ANALIZAR_CAMARA && !this.userExplicitlyRequestedVision()) {
        cedRealtimeLog("tool.analyze_camera.blocked", {
          last: this.lastMeaningfulUserUtterance.slice(0, 60),
        });
        await this.submitToolOutput(callId, { status: "ignored", silent: true });
        return;
      }

      if (name === ACTIVAR_PROSPECCION && userExplicitlyRequestedProspection(this.lastMeaningfulUserUtterance)) {
        cedRealtimeLog("tool.prospection.client_handled", {
          last: this.lastMeaningfulUserUtterance.slice(0, 60),
        });
        await this.submitToolOutput(callId, { status: "ok", silent: true });
        return;
      }

      if (name === ACTIVAR_PROSPECCION && !userExplicitlyRequestedProspection(this.lastMeaningfulUserUtterance)) {
        cedRealtimeLog("tool.prospection.blocked", {
          last: this.lastMeaningfulUserUtterance.slice(0, 60),
        });
        await this.submitToolOutput(callId, {
          status: "ignored",
          spoken: "No se activó prospección: el usuario no lo pidió explícitamente.",
        });
        return;
      }

      if (name === DESACTIVAR_PROSPECCION && !isProspectionOffIntent(this.lastMeaningfulUserUtterance)) {
        cedRealtimeLog("tool.prospection_off.blocked", {
          last: this.lastMeaningfulUserUtterance.slice(0, 60),
        });
        await this.submitToolOutput(callId, { status: "ignored", silent: true });
        return;
      }

      if (name === REPORTE_PROSPECCION && !isProspectionReportIntent(this.lastMeaningfulUserUtterance)) {
        cedRealtimeLog("tool.prospection_report.blocked", {
          last: this.lastMeaningfulUserUtterance.slice(0, 60),
        });
        await this.submitToolOutput(callId, { status: "ignored", silent: true });
        return;
      }

      if (name === LEER_COMENTARIOS_REDES) {
        h.onToolStart?.(name);
        const platRaw = String(args.platform ?? "both").trim().toLowerCase();
        const platform =
          platRaw === "instagram" || platRaw === "ig"
            ? "instagram"
            : platRaw === "facebook" || platRaw === "fb"
              ? "facebook"
              : socialCommentPlatform(this.lastMeaningfulUserUtterance);
        const r = await fetchSocialComments(platform);
        const spoken = r.ok
          ? r.spoken
          : r.error || "No fue posible consultar los comentarios.";
        await this.submitToolOutput(callId, {
          status: r.ok ? "ok" : "error",
          spoken,
          platform,
          success: r.ok,
        });
        return;
      }

      if (LIVE_TOOL_NAMES.has(name) && h.onLiveTool) {
        h.onToolStart?.(name);
        const result = await h.onLiveTool(name, args);
        const success = result?.ok !== false;
        let spoken = (result?.spoken ?? "").trim();
        if (name === PUBLICAR_FACEBOOK) {
          spoken = success
            ? cedPublishSuccessPhrase("facebook", this.userAddress)
            : cedPublishFailurePhrase(spoken || "no fue posible completar la publicación", this.userAddress);
        } else if (name === PUBLICAR_INSTAGRAM) {
          spoken = success
            ? cedPublishSuccessPhrase("instagram", this.userAddress)
            : cedPublishFailurePhrase(spoken || "no fue posible completar la publicación", this.userAddress);
        } else if (!spoken) {
          spoken = success ? "Operación completada." : "No pude completar la operación.";
        }
        const toolResult = {
          status: success ? "ok" : "error",
          spoken,
          success,
        };
        this.dispatchVoiceToolResult(name, toolResult);
        await this.submitToolOutput(callId, toolResult);
        return;
      }

      const unknown = { status: "unknown_tool", name: rawName };
      cedRealtimeLog("tool.unknown", { name: rawName });
      await this.submitToolOutput(callId, unknown);
    } catch (error) {
      cedVoiceError("[REALTIME] tool execution failed", error);
      const message = error instanceof Error ? error.message : "Error al ejecutar herramienta";
      await this.submitToolOutput(callId, {
        status: "error",
        spoken: message,
        success: false,
      });
    } finally {
      h.onToolComplete?.();
    }
  }

  private async submitToolOutput(
    callId: string,
    output: Record<string, unknown>,
  ): Promise<void> {
    if (this.responseInProgress && !output.advancedBrief) {
      cedRealtimeLog("tool.output.wait_idle", { call_id: callId });
      await this.waitForResponseIdle(1600);
    }
    const spoken =
      typeof output.spoken === "string" ? output.spoken.trim() : "";
    const briefOnly = output.briefOnly === true;
    const advancedBrief = output.advancedBrief === true;
    const silent = output.silent === true;
    const payload: Record<string, unknown> = {
      status: output.status,
      success: output.status === "ok" || output.success === true,
    };
    if (output.prompt) payload.prompt = output.prompt;
    if (spoken) {
      payload.spoken = spoken;
      payload.delivery =
        "SILENCIO OBLIGATORIO. NO narres ni resumas este resultado en voz. " +
        "El cliente leerá el texto vía [CED_BRIEF]. Permanece en silencio.";
    }

    const outputMessage = {
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: callId,
        output: JSON.stringify(payload),
      },
    };
    cedRealtimeLog("tool.output.send", { call_id: callId, payload });
    this.send(outputMessage);

    if (spoken && (briefOnly || advancedBrief)) {
      cedRealtimeLog("tool.response.brief", { call_id: callId, advanced: advancedBrief });
      const turn = advancedBrief ? cedAdvancedBriefTurn(spoken) : cedBriefTurn(spoken);
      const tokens = this.briefTokensForSpoken(spoken, advancedBrief);
      this.turnCooldownUntil = Date.now() + Math.min(18000, 5000 + spoken.length * 12);
      await this.enqueueControlledBrief(turn, tokens);
      return;
    }

    if (!silent) {
      cedRealtimeLog("tool.response.create", { call_id: callId });
      this.send({ type: "response.create" });
    }
  }
}

