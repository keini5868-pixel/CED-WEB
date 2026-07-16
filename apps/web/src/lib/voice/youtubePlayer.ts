/**
 * Puente frontend del reproductor de YouTube por voz (Fase 1).
 *
 * El backend empuja acciones `youtube_play|pause|resume|close` por
 * `voice/client-state` (tool_events + client_action). El hook de voz las
 * convierte en un CustomEvent de ventana que consume CedYoutubePlayerPanel.
 */

export const CED_YOUTUBE_EVENT = "ced-youtube-event";

export type CedYoutubeVideo = {
  videoId: string;
  title: string;
  channelTitle?: string;
  thumbnailUrl?: string;
};

export type CedYoutubeAction =
  | { action: "play"; video: CedYoutubeVideo }
  | { action: "pause" }
  | { action: "resume" }
  | { action: "close" };

/** IDs de video de YouTube: exactamente 11 caracteres [A-Za-z0-9_-]. */
const VIDEO_ID_RE = /^[A-Za-z0-9_-]{11}$/;

export function isValidYoutubeVideoId(value: unknown): value is string {
  return typeof value === "string" && VIDEO_ID_RE.test(value);
}

export const YOUTUBE_EMBED_ORIGIN = "https://www.youtube-nocookie.com";

/**
 * URL de embed oficial (dominio nocookie) con la IFrame API habilitada.
 * `videoId` debe validarse antes; se rechaza cualquier otro valor.
 */
export function buildYoutubeEmbedUrl(videoId: string, pageOrigin?: string): string | null {
  if (!isValidYoutubeVideoId(videoId)) return null;
  const params = new URLSearchParams({
    enablejsapi: "1",
    autoplay: "1",
    playsinline: "1",
    rel: "0",
    modestbranding: "1",
  });
  if (pageOrigin) params.set("origin", pageOrigin);
  return `${YOUTUBE_EMBED_ORIGIN}/embed/${videoId}?${params.toString()}`;
}

/**
 * Convierte un tool_event/payload del backend en una acción tipada.
 * Devuelve null si el evento no es de YouTube o el video_id es inválido.
 */
export function youtubeActionFromBridge(
  type: string,
  data: Record<string, unknown> | undefined,
): CedYoutubeAction | null {
  if (type === "youtube_pause") return { action: "pause" };
  if (type === "youtube_resume") return { action: "resume" };
  if (type === "youtube_close") return { action: "close" };
  if (type !== "youtube_play") return null;
  const videoId = data?.video_id;
  if (!isValidYoutubeVideoId(videoId)) return null;
  const title = typeof data?.title === "string" ? data.title : "";
  const channelTitle =
    typeof data?.channel_title === "string" && data.channel_title
      ? data.channel_title
      : undefined;
  const thumbnailUrl =
    typeof data?.thumbnail_url === "string" &&
    /^https:\/\//.test(data.thumbnail_url)
      ? data.thumbnail_url
      : undefined;
  return {
    action: "play",
    video: { videoId, title, channelTitle, thumbnailUrl },
  };
}

export function isYoutubeBridgeAction(type: string): boolean {
  return (
    type === "youtube_play" ||
    type === "youtube_pause" ||
    type === "youtube_resume" ||
    type === "youtube_close"
  );
}

export function dispatchCedYoutubeEvent(detail: CedYoutubeAction): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<CedYoutubeAction>(CED_YOUTUBE_EVENT, { detail }));
}

/** Estados del player según la IFrame API (info.playerState). */
export const YT_STATE = {
  unstarted: -1,
  ended: 0,
  playing: 1,
  paused: 2,
  buffering: 3,
  cued: 5,
} as const;

type YoutubeCommand = "playVideo" | "pauseVideo" | "stopVideo" | "unMute" | "setVolume";

/**
 * Envía un comando oficial de la IFrame API vía postMessage al embed
 * (requiere enablejsapi=1). No necesita cargar el script externo de YouTube.
 */
export function postYoutubeCommand(
  iframe: HTMLIFrameElement | null,
  func: YoutubeCommand,
  args: unknown[] = [],
): void {
  const target = iframe?.contentWindow;
  if (!target) return;
  target.postMessage(
    JSON.stringify({ event: "command", func, args }),
    YOUTUBE_EMBED_ORIGIN,
  );
}

/** Volumen 0–100 del embed (máximo = menos “apagado” vs YouTube nativo). */
export function postYoutubeSetVolume(
  iframe: HTMLIFrameElement | null,
  volume: number,
): void {
  const v = Math.max(0, Math.min(100, Math.round(volume)));
  postYoutubeCommand(iframe, "setVolume", [v]);
}

/** Asegura audio a tope en el iframe (USB/carro + sesión de voz tienden a comprimirlo). */
export function boostYoutubeEmbedAudio(iframe: HTMLIFrameElement | null): void {
  postYoutubeUnMute(iframe);
  postYoutubeSetVolume(iframe, 100);
}

export function postYoutubeUnMute(iframe: HTMLIFrameElement | null): void {
  postYoutubeCommand(iframe, "unMute");
}

/** Handshake para que el embed empiece a emitir infoDelivery/onReady. */
export function postYoutubeListening(iframe: HTMLIFrameElement | null): void {
  const target = iframe?.contentWindow;
  if (!target) return;
  target.postMessage(
    JSON.stringify({ event: "listening", id: "ced-youtube", channel: "widget" }),
    YOUTUBE_EMBED_ORIGIN,
  );
}

/**
 * Evento de ventana: silenciar solo el TTS del agente mientras suena YouTube
 * (Opción A — mic activo para mandos por voz). No termina la llamada.
 */
export const CED_YOUTUBE_MEDIA_MODE_EVENT = "ced-youtube-media-mode";

export function dispatchYoutubeMediaMode(active: boolean): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(CED_YOUTUBE_MEDIA_MODE_EVENT, { detail: { active } }),
  );
}

/**
 * Extrae playerState de un message event del embed. Devuelve null si el
 * mensaje no proviene del embed o no incluye estado.
 */
export function parseYoutubePlayerState(event: {
  origin: string;
  data: unknown;
}): number | null {
  if (event.origin !== YOUTUBE_EMBED_ORIGIN) return null;
  let data: unknown = event.data;
  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      return null;
    }
  }
  if (!data || typeof data !== "object") return null;
  const info = (data as { info?: unknown }).info;
  if (!info || typeof info !== "object") return null;
  const state = (info as { playerState?: unknown }).playerState;
  return typeof state === "number" ? state : null;
}
