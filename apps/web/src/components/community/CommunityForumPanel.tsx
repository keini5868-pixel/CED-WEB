"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { CedButton } from "@ced/ui";

import {
  createCommunityPost,
  fetchCommunityMeta,
  fetchCommunityPosts,
  reactCommunityPost,
  replyCommunityPost,
  reportCommunityPost,
  saveCommunityToken,
  type CommunityMeta,
  type CommunityPost,
  type CommunityRoomId,
} from "@/lib/api/community";
import { COMMUNITY_TOKENS, tokenSrc } from "@/lib/community/tokens";

function TokenFace({
  id,
  size = 44,
  title,
}: {
  id: string;
  size?: number;
  title?: string;
}) {
  return (
    <span
      className="relative inline-flex shrink-0 overflow-hidden rounded-full border border-cyan-400/35 bg-black shadow-[0_0_18px_rgba(34,211,238,0.22)]"
      style={{ width: size, height: size }}
      title={title}
    >
      {/* Recorte: las fichas generadas a veces traen caption abajo */}
      <img
        src={tokenSrc(id)}
        alt=""
        className="absolute inset-[-8%_-8%_12%_-8%] h-[120%] w-[116%] object-cover object-[center_28%]"
      />
    </span>
  );
}

function ago(iso: string): string {
  const t = new Date(iso).getTime();
  if (!t) return "";
  const min = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (min < 1) return "ahora";
  if (min < 60) return `${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} h`;
  return `${Math.round(h / 24)} d`;
}

export function CommunityForumPanel() {
  const [meta, setMeta] = useState<CommunityMeta | null>(null);
  const [room, setRoom] = useState<CommunityRoomId | "">("");
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [token, setToken] = useState("listo");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [reply, setReply] = useState("");

  const load = useCallback(async (nextRoom?: string) => {
    const [m, list] = await Promise.all([
      fetchCommunityMeta(),
      fetchCommunityPosts(nextRoom || undefined),
    ]);
    setMeta(m);
    if (m.me.token) setToken(m.me.token);
    else setPicking(true);
    setPosts(list);
  }, []);

  useEffect(() => {
    void load().catch((err: Error) => setError(err.message));
  }, [load]);

  const rooms = meta?.rooms || [];
  const meName = meta?.me.display_name || "Operador";

  const filtered = useMemo(
    () => (room ? posts.filter((p) => p.room === room) : posts),
    [posts, room],
  );

  async function chooseToken(id: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await saveCommunityToken(id);
      setToken(res.me.token);
      setPicking(false);
      setMeta((prev) => (prev ? { ...prev, me: res.me } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar la ficha.");
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const res = await createCommunityPost({
        room: room || "ayuda",
        title,
        body,
        token,
      });
      setPosts((prev) => [res.post, ...prev]);
      setTitle("");
      setBody("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo publicar.");
    } finally {
      setBusy(false);
    }
  }

  async function sendReply(postId: string) {
    if (!reply.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await replyCommunityPost(postId, reply, token);
      setPosts((prev) =>
        prev.map((p) =>
          p.id === postId
            ? { ...p, replies: [...p.replies, res.reply], reply_count: p.reply_count + 1 }
            : p,
        ),
      );
      setReply("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo responder.");
    } finally {
      setBusy(false);
    }
  }

  async function react(postId: string, id: string) {
    try {
      const res = await reactCommunityPost(postId, id);
      setPosts((prev) =>
        prev.map((p) => (p.id === postId ? { ...p, reactions: res.reactions } : p)),
      );
    } catch {
      /* silent */
    }
  }

  async function report(postId: string) {
    await reportCommunityPost(postId);
    setPosts((prev) => prev.filter((p) => p.id !== postId));
  }

  return (
    <div className="ced-hud-page-bg relative flex h-full min-h-0 flex-col overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent" />

      <header className="flex shrink-0 flex-wrap items-end justify-between gap-4 border-b border-cyan-500/20 px-4 py-5 sm:px-8">
        <div>
          <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.38em] text-cyan-400">
            SALA CED
          </p>
          <h1 className="mt-1 font-[family-name:var(--font-orbitron)] text-2xl text-cyan-50 sm:text-4xl">
            La mesa de operadores
          </h1>
          <p className="mt-2 max-w-xl text-sm text-cyan-200/70">
            Prompts, guiones, copies y ayuda. Sin privado. Las fichas son el
            mismo robot CED, cada gesto dice algo.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setPicking(true)}
          className="flex items-center gap-3 rounded-full border border-cyan-500/30 bg-black/40 px-3 py-2"
        >
          <TokenFace id={token} size={52} />
          <span className="text-left">
            <span className="block font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest text-cyan-500">
              TU FICHA
            </span>
            <span className="block text-sm text-cyan-100">{meName}</span>
          </span>
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden px-4 py-4 sm:px-8 lg:flex-row">
        <aside className="flex shrink-0 flex-col gap-2 lg:w-56">
          <button
            type="button"
            onClick={() => {
              setRoom("");
              void load("").catch(() => undefined);
            }}
            className={[
              "rounded-lg border px-3 py-3 text-left",
              !room
                ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-50"
                : "border-cyan-900/60 text-cyan-300 hover:border-cyan-600",
            ].join(" ")}
          >
            <span className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest">
              TODA LA SALA
            </span>
          </button>
          {rooms.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => {
                setRoom(r.id);
                void load(r.id).catch((err: Error) => setError(err.message));
              }}
              className={[
                "rounded-lg border px-3 py-3 text-left",
                room === r.id
                  ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-50"
                  : "border-cyan-900/60 text-cyan-300 hover:border-cyan-600",
              ].join(" ")}
            >
              <span className="block font-[family-name:var(--font-orbitron)] text-[11px] tracking-widest">
                {r.label.toUpperCase()}
              </span>
              <span className="mt-1 block text-xs text-cyan-500">{r.hint}</span>
            </button>
          ))}
          <div className="mt-3 hidden rounded-lg border border-amber-500/20 bg-amber-950/20 p-3 text-[11px] leading-relaxed text-amber-100/80 lg:block">
            {(meta?.rules || []).map((rule) => (
              <p key={rule} className="mb-2 last:mb-0">
                {rule}
              </p>
            ))}
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
          <div className="rounded-xl border border-cyan-500/25 bg-black/35 p-4 shadow-[0_0_40px_rgba(34,211,238,0.06)]">
            <div className="mb-3 flex items-center gap-3">
              <TokenFace id={token} size={40} />
              <p className="text-xs text-cyan-400/80">
                Publicas como {meName} en{" "}
                <span className="text-cyan-200">
                  {rooms.find((r) => r.id === room)?.label || "Ayuda"}
                </span>
              </p>
            </div>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={80}
              placeholder="Título corto (opcional)"
              className="mb-2 w-full rounded-md border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50 outline-none placeholder:text-cyan-800 focus:border-cyan-500"
            />
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={1200}
              rows={3}
              placeholder="Comparte un prompt, un guion, un copy o una duda. Sin teléfonos ni links raros."
              className="w-full resize-none rounded-md border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50 outline-none placeholder:text-cyan-800 focus:border-cyan-500"
            />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <p className="text-[11px] text-cyan-700">{body.length}/1200</p>
              <CedButton onClick={() => void publish()} disabled={busy || !body.trim()}>
                Publicar en la sala
              </CedButton>
            </div>
          </div>

          {error ? (
            <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
              {error}
            </p>
          ) : null}

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <TokenFace id="pensar" size={72} />
                <p className="mt-4 font-[family-name:var(--font-orbitron)] text-sm tracking-widest text-cyan-300">
                  La mesa está en silencio
                </p>
                <p className="mt-2 max-w-sm text-sm text-cyan-500">
                  Sé el primero en dejar un prompt o una duda. Los operadores
                  llegan por las fichas.
                </p>
              </div>
            ) : null}

            {filtered.map((post) => (
              <article
                key={post.id}
                className="rounded-xl border border-cyan-900/50 bg-black/40 p-4"
              >
                <div className="flex gap-3">
                  <TokenFace id={post.token} size={48} title={post.display_name} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-cyan-100">
                        {post.display_name}
                      </span>
                      <span className="rounded border border-cyan-800 px-1.5 py-0.5 font-[family-name:var(--font-orbitron)] text-[9px] tracking-widest text-cyan-400">
                        {post.room}
                      </span>
                      <span className="text-[11px] text-cyan-700">{ago(post.created_at)}</span>
                    </div>
                    {post.title ? (
                      <h2 className="mt-1 font-[family-name:var(--font-orbitron)] text-sm text-cyan-50">
                        {post.title}
                      </h2>
                    ) : null}
                    <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-cyan-100/85">
                      {post.body}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      {COMMUNITY_TOKENS.map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => void react(post.id, t.id)}
                          className="group inline-flex items-center gap-1 rounded-full border border-cyan-900/70 px-1.5 py-0.5 hover:border-cyan-400/50"
                          title={t.label}
                        >
                          <TokenFace id={t.id} size={22} />
                          <span className="text-[10px] text-cyan-500">
                            {post.reactions[t.id] || ""}
                          </span>
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => setOpenId(openId === post.id ? null : post.id)}
                        className="ml-2 text-[11px] text-cyan-400 hover:text-cyan-100"
                      >
                        Responder · {post.reply_count}
                      </button>
                      <button
                        type="button"
                        onClick={() => void report(post.id)}
                        className="text-[11px] text-cyan-800 hover:text-amber-200"
                      >
                        Reportar
                      </button>
                    </div>
                    {openId === post.id ? (
                      <div className="mt-3 space-y-2 border-t border-cyan-900/50 pt-3">
                        {post.replies.map((r) => (
                          <div key={r.id} className="flex gap-2">
                            <TokenFace id={r.token} size={28} />
                            <div>
                              <p className="text-[11px] text-cyan-500">
                                {r.display_name} · {ago(r.created_at)}
                              </p>
                              <p className="text-sm text-cyan-100/90">{r.body}</p>
                            </div>
                          </div>
                        ))}
                        <div className="flex gap-2">
                          <input
                            value={reply}
                            onChange={(e) => setReply(e.target.value)}
                            placeholder="Respuesta corta, aquí en la sala."
                            className="flex-1 rounded-md border border-cyan-900/70 bg-black/50 px-3 py-2 text-sm text-cyan-50 outline-none focus:border-cyan-500"
                          />
                          <CedButton
                            variant="secondary"
                            onClick={() => void sendReply(post.id)}
                            disabled={busy || !reply.trim()}
                          >
                            Enviar
                          </CedButton>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>

      {picking ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
          <div className="w-full max-w-2xl rounded-2xl border border-cyan-400/30 bg-[#041018] p-6 shadow-[0_0_80px_rgba(34,211,238,0.18)]">
            <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-[0.35em] text-cyan-400">
              ELIGE TU FICHA
            </p>
            <h2 className="mt-2 font-[family-name:var(--font-orbitron)] text-2xl text-cyan-50">
              Un robot. Diez gestos.
            </h2>
            <p className="mt-2 text-sm text-cyan-300/80">
              Es el mismo CED. El gesto es cómo te van a reconocer en la mesa.
            </p>
            <div className="mt-6 grid grid-cols-5 gap-3">
              {COMMUNITY_TOKENS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  disabled={busy}
                  onClick={() => void chooseToken(t.id)}
                  className={[
                    "flex flex-col items-center gap-2 rounded-xl border p-2 transition",
                    token === t.id
                      ? "border-cyan-300 bg-cyan-400/10"
                      : "border-cyan-900/70 hover:border-cyan-500/50",
                  ].join(" ")}
                >
                  <TokenFace id={t.id} size={64} />
                  <span className="font-[family-name:var(--font-orbitron)] text-[9px] tracking-widest text-cyan-400">
                    {t.label.toUpperCase()}
                  </span>
                </button>
              ))}
            </div>
            {meta?.me.token ? (
              <button
                type="button"
                className="mt-5 text-xs text-cyan-600 hover:text-cyan-200"
                onClick={() => setPicking(false)}
              >
                Cerrar
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
