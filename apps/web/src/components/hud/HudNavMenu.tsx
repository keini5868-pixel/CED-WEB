"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  tone?: "hud" | "navy";
  hotspot?: string;
};

type MenuCoords = {
  top: number;
  left?: number;
  right?: number;
};

export function HudNavMenu({ label, items, align = "left", tone = "hud", hotspot }: HudNavMenuProps) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const [mounted, setMounted] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const visible = items.filter((item) => !item.hidden);

  useEffect(() => {
    setMounted(true);
  }, []);

  const updateCoords = useCallback(() => {
    const btn = buttonRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    setCoords(
      align === "right"
        ? { top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) }
        : { top: r.bottom + 6, left: Math.max(8, r.left) },
    );
  }, [align]);

  useLayoutEffect(() => {
    if (!open) return;
    updateCoords();
  }, [open, updateCoords]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (ev: MouseEvent) => {
      const target = ev.target as Node;
      if (buttonRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setOpen(false);
    };
    const onReposition = () => updateCoords();
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [open, updateCoords]);

  if (visible.length === 0) return null;

  const menu =
    mounted && open && coords
      ? createPortal(
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            style={{
              position: "fixed",
              top: coords.top,
              left: coords.left,
              right: coords.right,
            }}
            className="z-[200] min-w-[11.5rem] rounded-lg border border-cyan-500/30 bg-[#060b14] py-1 shadow-[0_12px_40px_rgba(0,0,0,0.65)]"
          >
            {visible.map((item) =>
              item.href ? (
                <Link
                  key={item.id}
                  href={item.href}
                  role="menuitem"
                  data-ced-hotspot={`nav-${item.id}`}
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
                  data-ced-hotspot={`nav-${item.id}`}
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
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        data-ced-hotspot={hotspot || label.toLowerCase()}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className={[
          "inline-flex items-center gap-1 rounded px-2 py-1.5 font-[family-name:var(--font-orbitron)] text-[10px] font-semibold uppercase tracking-wider sm:px-3 sm:text-xs",
          tone === "navy"
            ? "ced-mark-text hover:bg-white/10"
            : "text-cyan-400 hover:bg-cyan-400/10 hover:text-cyan-200",
        ].join(" ")}
      >
        {label}
        <ChevronDown
          className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`}
          strokeWidth={2}
        />
      </button>
      {menu}
    </div>
  );
}
