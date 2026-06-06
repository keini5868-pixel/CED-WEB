/** AudioContext singleton con unlock por gesto del usuario. */

export type AudioContextOptionsWithId = AudioContextOptions & { id?: string };

const contexts = new Map<string, AudioContext>();

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
    silent.src =
      "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
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
