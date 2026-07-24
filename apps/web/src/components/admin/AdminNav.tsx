"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchAdminSupportUnreadCount } from "@/lib/api/support";

const SUPPORT_CHAT_ENABLED =
  process.env.NEXT_PUBLIC_SUPPORT_CHAT_ENABLED !== "false";

const LINKS = [
  { href: "/admin", label: "Usuarios" },
  ...(SUPPORT_CHAT_ENABLED ? [{ href: "/admin/support", label: "Soporte" }] : []),
  { href: "/admin/monitoring", label: "Monitoreo" },
  { href: "/admin/pocket-option", label: "PO Demo" },
];

export function AdminNav() {
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!SUPPORT_CHAT_ENABLED) return;
    const load = async () => {
      try {
        setUnread(await fetchAdminSupportUnreadCount());
      } catch {
        /* ignore */
      }
    };
    void load();
    const t = window.setInterval(load, 30_000);
    return () => window.clearInterval(t);
  }, []);

  return (
    <nav className="flex flex-wrap gap-2 border-b border-cyan-500/20 bg-[#0a0a0a]/80 px-4 py-2">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        const isSupport = link.href === "/admin/support";
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`relative rounded px-3 py-1.5 text-xs font-medium tracking-wide transition ${
              active
                ? "bg-cyan-500/20 text-cyan-100"
                : "text-cyan-500/80 hover:bg-cyan-500/10 hover:text-cyan-200"
            }`}
          >
            {link.label}
            {isSupport && unread > 0 ? (
              <span className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                {unread > 9 ? "9+" : unread}
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
