"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

export type HudNavItem = {
  id: string;
  label: string;
  href?: string;
  onClick?: () => void;
  hidden?: boolean;
};

type HudNavMenuProps = {
  label: string;
  items: HudNavItem[];
  align?: "left" | "right";
};

export function HudNavMenu({ label, items, align = "left" }: HudNavMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const visible = items.filter((item) => !item.hidden);

  useEffect(() => {
    if (!open) return;
    const onDoc = (ev: MouseEvent) => {
      if (!rootRef.current?.contains(ev.target as Node)) setOpen(false);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (visible.length === 0) return null;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded px-2 py-1.5 font-[family-name:var(--font-orbitron)] text-[10px] font-semibold uppercase tracking-wider text-cyan-400 hover:bg-cyan-400/10 hover:text-cyan-200 sm:px-3 sm:text-xs"
      >
        {label}
        <ChevronDown
          className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`}
          strokeWidth={2}
        />
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          className={[
            "absolute top-[calc(100%+6px)] z-[80] min-w-[11.5rem] rounded-lg border border-cyan-500/30 bg-[#060b14]/98 py-1 shadow-xl backdrop-blur-md",
            align === "right" ? "right-0" : "left-0",
          ].join(" ")}
        >
          {visible.map((item) =>
            item.href ? (
              <Link
                key={item.id}
                href={item.href}
                role="menuitem"
                onClick={() => {
                  item.onClick?.();
                  setOpen(false);
                }}
                className="block px-3 py-2 text-left text-[11px] font-medium tracking-wide text-cyan-100/90 hover:bg-cyan-400/10 hover:text-cyan-50"
              >
                {item.label}
              </Link>
            ) : (
              <button
                key={item.id}
                type="button"
                role="menuitem"
                onClick={() => {
                  item.onClick?.();
                  setOpen(false);
                }}
                className="block w-full px-3 py-2 text-left text-[11px] font-medium tracking-wide text-cyan-100/90 hover:bg-cyan-400/10 hover:text-cyan-50"
              >
                {item.label}
              </button>
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}
