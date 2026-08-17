"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageCircle } from "lucide-react";
import { usePathname } from "next/navigation";

import SupportChatPanel from "@/components/support/SupportChatPanel";
import { useCedOverlay } from "@/contexts/CedOverlayContext";
import { useSupportUnreadPoll } from "@/hooks/useSupportUnreadPoll";
import { fetchUserSupportUnreadCount } from "@/lib/api/support";

export default function SupportFloatingButton() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const { textChatOpen } = useCedOverlay();

  const hidden =
    pathname?.startsWith("/admin") ||
    pathname?.startsWith("/login") ||
    pathname?.startsWith("/drive") ||
    pathname === "/dashboard" ||
    pathname === "/app" ||
    textChatOpen;

  const fetchCount = useCallback(() => fetchUserSupportUnreadCount(), []);
  const { unreadCount, setUnreadCount, refresh } = useSupportUnreadPoll(
    fetchCount,
    !hidden,
  );

  const handleMessageRead = useCallback(() => {
    setUnreadCount(0);
    void refresh();
  }, [refresh, setUnreadCount]);

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
          className="fixed bottom-[calc(5.5rem+env(safe-area-inset-bottom,0px))] right-[max(0.75rem,env(safe-area-inset-right))] z-[35] flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-purple-600 to-blue-600 shadow-2xl ring-2 ring-cyan-400/40 transition-transform hover:scale-110 sm:h-14 sm:w-14"
          aria-label="Soporte"
        >
          <MessageCircle className="text-white" size={24} />
          {unreadCount > 0 ? (
            <span className="absolute -right-1 -top-1 flex h-6 w-6 animate-pulse items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white ring-2 ring-[#0a0f18]">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          ) : null}
        </button>
      ) : null}

      {isOpen ? (
        <SupportChatPanel
          onClose={() => {
            setIsOpen(false);
            void refresh();
          }}
          onMessageRead={handleMessageRead}
        />
      ) : null}
    </>
  );
}
