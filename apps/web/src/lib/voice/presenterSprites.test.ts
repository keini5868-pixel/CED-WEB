import { describe, expect, it } from "vitest";

import type { PresenterGesture } from "./presenterGestures";
import { PRESENTER_GESTURE_IDS, PRESENTER_SPRITE_SLOTS, spriteUrl } from "./presenterSprites";

const ALL: PresenterGesture[] = [
  "idle",
  "welcome",
  "farewell",
  "think",
  "success",
  "serious",
  "laugh",
  "listen",
  "construct",
  "error",
  "ok",
  "point",
  "present",
  "sad",
  "stress",
  "zen",
  "look",
];

describe("presenterSprites", () => {
  it("tiene un slot de imagen por cada gesto emocional", () => {
    expect(PRESENTER_GESTURE_IDS.sort()).toEqual([...ALL].sort());
    for (const id of ALL) {
      expect(PRESENTER_SPRITE_SLOTS[id].file).toBe(`${id}.png`);
      expect(spriteUrl(id)).toContain(`/voice/ced-puppet/${id}.png`);
    }
  });
});
