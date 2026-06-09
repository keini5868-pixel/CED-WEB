"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

/** Modales admin sobre todo el HUD (evita que MI CUPO tape el formulario). */
export function AdminModalPortal({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  if (!mounted) return null;
  return createPortal(children, document.body);
}
