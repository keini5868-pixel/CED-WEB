"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CedButton, CedInput, CedModal } from "@ced/ui";

import {
  getConversationMessages,
  listConversations,
  type ConversationMessage,
  type ConversationRow,
} from "@/lib/api/conversations";

type ChannelFilter = "" | "voice" | "text";

export function HistorialConversaciones() {
  const [items, setItems] = useState<ConversationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [channel, setChannel] = useState<ChannelFilter>("");
  const [selected, setSelected] = useState<ConversationRow | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listConversations({
        limit: 50,
        channel: channel || undefined,
        q: search.trim() || undefined,
      });
      setItems(rows);
    } finally {
      setLoading(false);
    }
  }, [channel, search]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadList();
    }, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [loadList, search]);

  async function openConversation(conv: ConversationRow) {
    setSelected(conv);
    setDetailLoading(true);
    setMessages([]);
    try {
      const data = await getConversationMessages(conv.id);
      setMessages(data.messages);
    } catch {
      setMessages([]);
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-[family-name:var(--font-orbitron)] text-lg font-bold text-cyan-300">
            HISTORIAL
          </h1>
          <p className="ced-hud-text-muted mt-1 text-sm">
            Conversaciones de voz y chat guardadas en Supabase.
          </p>
        </div>
        <Link
          href="/dashboard"
          className="text-xs text-cyan-600 hover:text-cyan-400"
        >
          ← Dashboard
        </Link>
      </div>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row">
        <CedInput
          label="Buscar"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Texto en conversaciones…"
        />
        <label className="flex flex-col gap-1 text-xs text-cyan-600">
          Tipo
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value as ChannelFilter)}
            className="rounded border border-cyan-900/60 bg-black px-3 py-2 text-sm text-cyan-100"
          >
            <option value="">Todos</option>
            <option value="voice">Voz</option>
            <option value="text">Texto</option>
          </select>
        </label>
      </div>

      {loading ? (
        <p className="ced-hud-text-muted text-sm">Cargando…</p>
      ) : items.length === 0 ? (
        <p className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-4 text-sm">
          No hay conversaciones guardadas aún.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => void openConversation(c)}
                className="w-full rounded border border-cyan-900/50 bg-[#0a0a0a] p-4 text-left transition hover:border-cyan-500/40"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-cyan-200">{c.title}</p>
                  <span className="rounded bg-cyan-950 px-2 py-0.5 text-[10px] uppercase text-cyan-500">
                    {c.channel === "text" ? "Texto" : "Voz"}
                  </span>
                </div>
                {c.preview ? (
                  <p className="ced-hud-text-muted mt-2 line-clamp-2 text-xs">{c.preview}</p>
                ) : null}
                <p className="ced-hud-text-muted mt-2 text-[10px]">
                  {new Date(c.updated_at).toLocaleString("es-MX")}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}

      <CedModal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.title ?? "Conversación"}
        footer={
          <CedButton variant="ghost" onClick={() => setSelected(null)}>
            CERRAR
          </CedButton>
        }
      >
        {detailLoading ? (
          <p className="ced-hud-text-muted text-sm">Cargando mensajes…</p>
        ) : messages.length === 0 ? (
          <p className="ced-hud-text-muted text-sm">Sin mensajes en esta conversación.</p>
        ) : (
          <ul className="max-h-[60vh] space-y-3 overflow-y-auto pr-1 text-sm">
            {messages.map((m) => {
              const isUser = m.role === "user";
              return (
                <li
                  key={m.id}
                  className={`rounded border p-3 ${
                    isUser
                      ? "border-cyan-900/40 bg-cyan-950/20"
                      : "border-cyan-500/20 bg-black"
                  }`}
                >
                  <p className="mb-1 text-[10px] uppercase tracking-widest text-cyan-600">
                    {isUser ? "Tú" : "CED"} ·{" "}
                    {m.created_at
                      ? new Date(m.created_at).toLocaleString("es-MX")
                      : ""}
                  </p>
                  <p className="whitespace-pre-wrap text-cyan-100">{m.content}</p>
                </li>
              );
            })}
          </ul>
        )}
      </CedModal>
    </div>
  );
}
