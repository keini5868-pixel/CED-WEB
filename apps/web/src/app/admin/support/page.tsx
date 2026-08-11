"use client";

import { useState } from "react";
import { Headphones, MessageSquareWarning } from "lucide-react";
import { HudPanel } from "@ced/ui";

import { AdminSupportInbox } from "@/components/admin/AdminSupportInbox";
import { AdminInsightForum } from "@/components/support/AdminInsightForum";

type Tab = "inbox" | "insights";

export default function AdminSupportPage() {
  const [tab, setTab] = useState<Tab>("insights");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setTab("insights")}
          className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold tracking-wide ${
            tab === "insights"
              ? "bg-amber-500/25 text-amber-100"
              : "bg-cyan-500/10 text-cyan-400/80 hover:bg-cyan-500/15"
          }`}
        >
          <MessageSquareWarning className="h-3.5 w-3.5" />
          Foro dudas
        </button>
        <button
          type="button"
          onClick={() => setTab("inbox")}
          className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold tracking-wide ${
            tab === "inbox"
              ? "bg-amber-500/25 text-amber-100"
              : "bg-cyan-500/10 text-cyan-400/80 hover:bg-cyan-500/15"
          }`}
        >
          <Headphones className="h-3.5 w-3.5" />
          Inbox chat
        </button>
      </div>

      {tab === "insights" ? (
        <HudPanel
          title="FORO DUDAS — AUTO-CAPTURADAS"
          className="col-span-full min-h-[28rem] border-0 bg-transparent p-0 shadow-none"
        >
          <div className="h-[min(70vh,36rem)] overflow-hidden rounded-xl border border-amber-500/25 bg-[#0a0f18]">
            <AdminInsightForum />
          </div>
        </HudPanel>
      ) : (
        <HudPanel
          title="SOPORTE — CONVERSACIONES"
          className="col-span-full border-0 bg-transparent p-0 shadow-none"
        >
          <AdminSupportInbox />
        </HudPanel>
      )}
    </div>
  );
}
