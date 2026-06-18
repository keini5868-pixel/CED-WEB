"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Headphones, X } from "lucide-react";

import { AdminSupportInbox } from "@/components/admin/AdminSupportInbox";

type Props = {
  onClose: () => void;
  onUnreadChange: (count: number) => void;
};

export function AdminSupportFloatingPanel({ onClose, onUnreadChange }: Props) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[130] flex flex-col overflow-hidden border-amber-500/40 bg-[#0a0f18] shadow-2xl sm:inset-auto sm:bottom-24 sm:left-6 sm:h-[min(640px,calc(100vh-6rem))] sm:w-[min(720px,calc(100vw-1.5rem))] sm:rounded-2xl sm:border">
      <header className="flex shrink-0 items-center justify-between border-b border-amber-500/25 bg-gradient-to-r from-amber-900/30 to-purple-900/30 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:py-3">
        <div className="flex items-center gap-2">
          <Headphones className="h-4 w-4 text-amber-300" />
          <div>
            <p className="font-[family-name:var(--font-orbitron)] text-sm font-bold text-amber-200">
              Soporte — Admin
            </p>
            <p className="text-[10px] text-amber-500/80">
              Conversaciones de usuarios
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-amber-300 hover:bg-amber-500/10"
          aria-label="Cerrar"
        >
          <X size={18} />
        </button>
      </header>
      <div className="min-h-0 flex-1">
        <AdminSupportInbox compact onUnreadCountChange={onUnreadChange} />
      </div>
    </div>,
    document.body,
  );
}
