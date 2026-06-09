/** AudioContext singleton con unlock por gesto del usuario. */

export type AudioContextOptionsWithId = AudioContextOptions & { id?: string };

const contexts = new Map<string, AudioContext>();

const SILENT_WAV =
  "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";

/** Llamar al inicio del tap en mic — sin await — para iOS/Android. */
export function unlockVoiceAudioOnGesture(): void {
  const unlock = new Promise<void>((resolve) => {
    window.addEventListener("touchstart", () => resolve(), { once: true, passive: true });
    window.addEventListener("pointerdown", () => resolve(), { once: true });
    window.addEventListener("keydown", () => resolve(), { once: true });
  });

  const resumeAll = () => {
    for (const ctx of contexts.values()) {
      if (ctx.state === "suspended") void ctx.resume();
    }
  };

  try {
    const silent = new Audio();
    silent.src = SILENT_WAV;
    silent.setAttribute("playsinline", "true");
    void silent.play().then(resumeAll).catch(() => unlock.then(resumeAll));
  } catch {
    void unlock.then(resumeAll);
  }

  for (const spec of [
    { id: "ced-out", sampleRate: 24000, latencyHint: "playback" as const },
    { id: "ced-mic", latencyHint: "interactive" as const },
  ]) {
    const { id, ...opts } = spec;
    if (!contexts.has(id)) {
      try {
        contexts.set(id, new AudioContext(opts));
      } catch {
        /* ignore */
      }
    }
    const ctx = contexts.get(id);
    if (ctx?.state === "suspended") void ctx.resume();
  }
}

export async function getAudioContext(
  options?: AudioContextOptionsWithId,
): Promise<AudioContext> {
  const id = options?.id;
  if (id && contexts.has(id)) {
    const existing = contexts.get(id)!;
    if (existing.state === "suspended") await existing.resume();
    return existing;
  }

  const unlock = new Promise<void>((resolve) => {
    window.addEventListener("touchstart", () => resolve(), { once: true, passive: true });
    window.addEventListener("pointerdown", () => resolve(), { once: true });
    window.addEventListener("keydown", () => resolve(), { once: true });
  });

  const create = () => {
    const { id: _id, ...ctxOpts } = options ?? {};
    const ctx = new AudioContext(ctxOpts);
    if (id) contexts.set(id, ctx);
    return ctx;
  };

  try {
    const silent = new Audio();
    silent.src = SILENT_WAV;
    silent.setAttribute("playsinline", "true");
    await silent.play();
    const ctx = create();
    if (ctx.state === "suspended") await ctx.resume();
    return ctx;
  } catch {
    await unlock;
    const ctx = create();
    if (ctx.state === "suspended") await ctx.resume();
    return ctx;
  }
}

export async function closeAudioContext(id: string): Promise<void> {
  const ctx = contexts.get(id);
  if (!ctx) return;
  contexts.delete(id);
  await ctx.close();
}
