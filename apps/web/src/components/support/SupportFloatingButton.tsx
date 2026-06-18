"use client";

import { useEffect, useState } from "react";
import { MessageCircle, X } from "lucide-react";
import { usePathname } from "next/navigation";

import SupportChatPanel from "@/components/support/SupportChatPanel";
import { fetchUserSupportUnreadCount } from "@/lib/api/support";

export default function SupportFloatingButton() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const hidden =
    pathname?.startsWith("/admin") ||
    pathname?.startsWith("/login") ||
    pathname?.startsWith("/drive");

  useEffect(() => {
    if (hidden) return;
    const checkUnread = async () => {
      try {
        const count = await fetchUserSupportUnreadCount();
        setUnreadCount(count);
      } catch {
        /* ignore */
      }
    };
    void checkUnread();
    const interval = window.setInterval(checkUnread, 30_000);
    return () => window.clearInterval(interval);
  }, [hidden]);

  if (hidden) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="fixed bottom-6 right-6 z-[120] flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-purple-600 to-blue-600 shadow-2xl ring-2 ring-cyan-400/40 transition-transform hover:scale-110 sm:bottom-8 sm:right-8"
        aria-label="Soporte"
      >
        {isOpen ? (
          <X className="text-white" size={24} />
        ) : (
          <>
            <MessageCircle className="text-white" size={24} />
            {unreadCount > 0 ? (
              <span className="absolute -right-1 -top-1 flex h-6 w-6 animate-pulse items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            ) : null}
          </>
        )}
      </button>

      {isOpen ? (
        <SupportChatPanel
          onClose={() => setIsOpen(false)}
          onMessageRead={() => setUnreadCount(0)}
        />
      ) : null}
    </>
  );
}
