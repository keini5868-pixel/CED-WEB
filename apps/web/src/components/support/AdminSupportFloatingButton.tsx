"use client";

import { useCallback, useEffect, useState } from "react";
import { Headphones } from "lucide-react";
import { usePathname } from "next/navigation";

import { AdminSupportFloatingPanel } from "@/components/support/AdminSupportFloatingPanel";
import { useCedOverlay } from "@/contexts/CedOverlayContext";
import { useSupportUnreadPoll } from "@/hooks/useSupportUnreadPoll";
import { fetchAdminSupportUnreadCount } from "@/lib/api/support";

export default function AdminSupportFloatingButton() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const { textChatOpen } = useCedOverlay();

  const hidden =
    pathname?.startsWith("/login") ||
    pathname?.startsWith("/drive") ||
    textChatOpen;

  const fetchCount = useCallback(() => fetchAdminSupportUnreadCount(), []);
  const { unreadCount, setUnreadCount, refresh } = useSupportUnreadPoll(
    fetchCount,
    !hidden,
  );

  const handleUnreadChange = useCallback(
    (count: number) => {
      setUnreadCount(count);
    },
    [setUnreadCount],
  );

  useEffect(() => {
    if (textChatOpen) setIsOpen(false);
  }, [textChatOpen]);

  if (hidden) return null;

  return (
    <>
      {!isOpen ? (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="fixed bottom-[max(1.5rem,env(safe-area-inset-bottom))] left-[max(1.5rem,env(safe-area-inset-left))] z-[110] flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-amber-600 to-purple-700 shadow-2xl ring-2 ring-amber-400/50 transition-transform hover:scale-110 sm:bottom-8 sm:left-8"
          aria-label="Soporte administrador"
        >
          <Headphones className="text-white" size={24} />
          {unreadCount > 0 ? (
            <span className="absolute -right-1 -top-1 flex h-6 w-6 animate-pulse items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white ring-2 ring-[#0a0f18]">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          ) : null}
        </button>
      ) : null}

      {isOpen ? (
        <AdminSupportFloatingPanel
          onClose={() => {
            setIsOpen(false);
            void refresh();
          }}
          onUnreadChange={handleUnreadChange}
        />
      ) : null}
    </>
  );
}
