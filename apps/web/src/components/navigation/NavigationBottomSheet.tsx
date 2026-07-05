"use client";

import type { ReactNode } from "react";
import { X } from "lucide-react";

type NavigationBottomSheetProps = {
  title: string;
  onClose?: () => void;
  children: ReactNode;
  className?: string;
};

export function NavigationBottomSheet({
  title,
  onClose,
  children,
  className = "",
}: NavigationBottomSheetProps) {
  return (
    <div
      className={`pointer-events-auto fixed inset-x-0 bottom-0 z-[115] flex max-h-[min(62vh,520px)] flex-col rounded-t-2xl bg-white text-gray-900 shadow-[0_-8px_40px_rgba(0,0,0,0.35)] ${className}`}
    >
      <div className="flex shrink-0 justify-center pt-2.5">
        <div className="h-1 w-10 rounded-full bg-gray-300" aria-hidden />
      </div>

      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <h2 className="truncate text-lg font-semibold text-gray-900">{title}</h2>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-full p-2 text-gray-500 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {children}
      </div>
    </div>
  );
}
