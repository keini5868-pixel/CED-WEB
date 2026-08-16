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
import { sendToTrash } from "@/lib/api/trash";
import { SelectToolbar, TrashIconButton } from "@/components/trash/TrashControls";
import { collapseStreamingMessages } from "@/lib/voice/collapseStreamingMessages";
import { coerceDisplayText } from "@/lib/display-text";

type ChannelFilter = "" | "voice" | "text";

export function HistorialConversaciones({
  embedded = false,
}: {
  embedded?: boolean;
}) {
  const [items, setItems] = useState<ConversationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [channel, setChannel] = useState<ChannelFilter>("");
  const [selected, setSelected] = useState<ConversationRow | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busyTrash, setBusyTrash] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const rows = await listConversations({
        limit: 50,
        channel: channel || undefined,
        q: search.trim() || undefined,
      });
      setItems(rows);
    } catch (e) {
      setItems([]);
      setListError(
        e instanceof Error
          ? e.message
          : "No se pudo cargar el historial.",
      );
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
      setMessages(collapseStreamingMessages(data.messages));
    } catch {
      setMessages([]);
    } finally {
      setDetailLoading(false);
    }
  }

  async function trashIds(ids: string[]) {
    if (ids.length === 0) return;
    setBusyTrash(true);
    try {
      await sendToTrash("conversation", ids);
      setItems((prev) => prev.filter((c) => !ids.includes(c.id)));
      setPicked(new Set());
      setSelecting(false);
      if (selected && ids.includes(selected.id)) setSelected(null);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "No se pudo enviar a la papelera.");
    } finally {
      setBusyTrash(false);
    }
  }

  return (
    <div className={embedded ? "" : "mx-auto max-w-3xl px-4 py-8"}>
      {embedded ? null : (
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
      )}

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

      <SelectToolbar
        selecting={selecting}
        selectedCount={picked.size}
        busy={busyTrash}
        onToggle={() => {
          setSelecting((v) => !v);
          setPicked(new Set());
        }}
        onTrash={() => void trashIds([...picked])}
      />
        <p className="ced-hud-text-muted text-sm">Cargando…</p>
      ) : listError ? (
        <div className="rounded border border-red-500/40 bg-red-950/30 p-4 text-sm text-red-200">
          <p>{listError}</p>
          <button
            type="button"
            onClick={() => void loadList()}
            className="mt-3 text-xs text-cyan-400 underline hover:text-cyan-200"
          >
            Reintentar
          </button>
        </div>
      ) : items.length === 0 ? (
        <p className="ced-hud-text-muted rounded border border-cyan-900/50 bg-[#0a0a0a] p-4 text-sm">
          No hay conversaciones guardadas aún. Las sesiones de voz y chat
          nuevas deberían aparecer aquí al cerrar o durante el uso.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((c) => (
            <li key={c.id} className="flex items-stretch gap-2">
              {selecting ? (
                <label className="flex items-center px-1">
                  <input
                    type="checkbox"
                    checked={picked.has(c.id)}
                    onChange={() => {
                      setPicked((prev) => {
                        const next = new Set(prev);
                        if (next.has(c.id)) next.delete(c.id);
                        else next.add(c.id);
                        return next;
                      });
                    }}
                  />
                </label>
              ) : null}
              <button
                type="button"
                onClick={() => void openConversation(c)}
                className="min-w-0 flex-1 rounded border border-cyan-900/50 bg-[#0a0a0a] p-4 text-left transition hover:border-cyan-500/40"
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
              {selecting ? null : (
                <div className="flex items-center">
                  <TrashIconButton
                    disabled={busyTrash}
                    onClick={() => void trashIds([c.id])}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <CedModal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.title ?? "Conversación"}
        footer={
          <div className="flex w-full items-center justify-between gap-2">
            <TrashIconButton
              disabled={busyTrash || !selected}
              onClick={() => {
                if (selected) void trashIds([selected.id]);
              }}
            />
            <CedButton variant="ghost" onClick={() => setSelected(null)}>
              CERRAR
            </CedButton>
          </div>
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
                  <p className="whitespace-pre-wrap text-cyan-100">
                    {coerceDisplayText(m.content)}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </CedModal>
    </div>
  );
}
