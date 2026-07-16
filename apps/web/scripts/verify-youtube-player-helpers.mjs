/**
 * Verificación manual de src/lib/voice/youtubePlayer.ts sin runner de tests
 * (vitest no está instalado en el workspace). Ejecutar con Node >= 23.6:
 *   node scripts/verify-youtube-player-helpers.mjs
 * Espeja los casos de src/lib/voice/youtubePlayer.test.ts.
 */
import assert from "node:assert/strict";

const mod = await import("../src/lib/voice/youtubePlayer.ts");
const {
  buildYoutubeEmbedUrl,
  isValidYoutubeVideoId,
  isYoutubeBridgeAction,
  parseYoutubePlayerState,
  YOUTUBE_EMBED_ORIGIN,
  youtubeActionFromBridge,
} = mod;

assert.equal(isValidYoutubeVideoId("dQw4w9WgXcQ"), true);
assert.equal(isValidYoutubeVideoId("a_b-C123456"), true);
assert.equal(isValidYoutubeVideoId(""), false);
assert.equal(isValidYoutubeVideoId("corto"), false);
assert.equal(isValidYoutubeVideoId("dQw4w9WgXcQextra"), false);
assert.equal(isValidYoutubeVideoId("../evil?a=1"), false);
assert.equal(isValidYoutubeVideoId('abc"><scri'), false);
assert.equal(isValidYoutubeVideoId(null), false);
assert.equal(isValidYoutubeVideoId(12345678901), false);

const url = buildYoutubeEmbedUrl("dQw4w9WgXcQ", "https://app.example.com");
assert.ok(url.startsWith(`${YOUTUBE_EMBED_ORIGIN}/embed/dQw4w9WgXcQ?`));
const params = new URL(url).searchParams;
assert.equal(params.get("enablejsapi"), "1");
assert.equal(params.get("autoplay"), "1");
assert.equal(params.get("origin"), "https://app.example.com");
assert.equal(buildYoutubeEmbedUrl("../../evil"), null);
assert.equal(buildYoutubeEmbedUrl("dQw4w9WgXcQ/extra"), null);

assert.deepEqual(
  youtubeActionFromBridge("youtube_play", {
    video_id: "dQw4w9WgXcQ",
    title: "Never Gonna Give You Up",
    channel_title: "Rick Astley",
    thumbnail_url: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
  }),
  {
    action: "play",
    video: {
      videoId: "dQw4w9WgXcQ",
      title: "Never Gonna Give You Up",
      channelTitle: "Rick Astley",
      thumbnailUrl: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    },
  },
);
assert.equal(youtubeActionFromBridge("youtube_play", { video_id: "<script>" }), null);
assert.equal(youtubeActionFromBridge("youtube_play", {}), null);
const noThumb = youtubeActionFromBridge("youtube_play", {
  video_id: "dQw4w9WgXcQ",
  title: "t",
  thumbnail_url: "javascript:alert(1)",
});
assert.equal(noThumb.video.thumbnailUrl, undefined);
assert.deepEqual(youtubeActionFromBridge("youtube_pause", undefined), { action: "pause" });
assert.deepEqual(youtubeActionFromBridge("youtube_resume", undefined), { action: "resume" });
assert.deepEqual(youtubeActionFromBridge("youtube_close", undefined), { action: "close" });
assert.equal(youtubeActionFromBridge("otro_evento", undefined), null);

assert.equal(isYoutubeBridgeAction("youtube_play"), true);
assert.equal(isYoutubeBridgeAction("youtube_close"), true);
assert.equal(isYoutubeBridgeAction("camera_capture"), false);

assert.equal(
  parseYoutubePlayerState({
    origin: YOUTUBE_EMBED_ORIGIN,
    data: JSON.stringify({ event: "infoDelivery", info: { playerState: 1 } }),
  }),
  1,
);
assert.equal(
  parseYoutubePlayerState({
    origin: "https://evil.example.com",
    data: JSON.stringify({ info: { playerState: 1 } }),
  }),
  null,
);
assert.equal(
  parseYoutubePlayerState({
    origin: YOUTUBE_EMBED_ORIGIN,
    data: JSON.stringify({ event: "onReady" }),
  }),
  null,
);
assert.equal(
  parseYoutubePlayerState({ origin: YOUTUBE_EMBED_ORIGIN, data: "no-json" }),
  null,
);

assert.equal(typeof mod.boostYoutubeEmbedAudio, "function");
assert.equal(typeof mod.dispatchYoutubeMediaMode, "function");
assert.equal(mod.CED_YOUTUBE_MEDIA_MODE_EVENT, "ced-youtube-media-mode");

console.log("OK: todos los asserts de youtubePlayer pasaron.");
