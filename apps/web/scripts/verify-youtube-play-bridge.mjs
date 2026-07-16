/**
 * Verifica bridge YouTube (client_action + tool_event) y IDs monotónicos.
 * node scripts/verify-youtube-play-bridge.mjs
 */
import assert from "node:assert/strict";

const mod = await import("../src/lib/voice/youtubePlayer.ts");
const {
  youtubeActionFromBridge,
  isYoutubeBridgeAction,
  buildYoutubeEmbedUrl,
  CED_YOUTUBE_MEDIA_MODE_EVENT,
} = mod;

// Simula payload de client_action (solo payload, sin type en raíz)
const fromAction = youtubeActionFromBridge("youtube_play", {
  video_id: "dQw4w9WgXcQ",
  title: "Never Gonna Give You Up",
  channel_title: "Rick Astley",
  thumbnail_url: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
});
assert.equal(fromAction?.action, "play");
assert.equal(fromAction?.video.videoId, "dQw4w9WgXcQ");

// Simula tool_event (type + campos en el mismo objeto)
const ev = {
  id: 1,
  type: "youtube_play",
  video_id: "dQw4w9WgXcQ",
  title: "Never Gonna Give You Up",
  channel_title: "Rick Astley",
  thumbnail_url: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
};
assert.equal(isYoutubeBridgeAction(ev.type), true);
const fromEvent = youtubeActionFromBridge(ev.type, ev);
assert.deepEqual(fromAction, fromEvent);

const embed = buildYoutubeEmbedUrl(
  "dQw4w9WgXcQ",
  "https://cedweb-production.up.railway.app",
);
assert.ok(embed?.includes("autoplay=1"));
assert.ok(embed?.includes("enablejsapi=1"));
assert.equal(CED_YOUTUBE_MEDIA_MODE_EVENT, "ced-youtube-media-mode");

// Invalid id must not open panel (anti basura)
assert.equal(
  youtubeActionFromBridge("youtube_play", { video_id: "nope" }),
  null,
);

console.log("OK: bridge client_action + tool_event listos para abrir panel.");
