"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

type CedOverlayContextValue = {
  textChatOpen: boolean;
  setTextChatOpen: (open: boolean) => void;
};

const CedOverlayContext = createContext<CedOverlayContextValue | null>(null);

export function CedOverlayProvider({ children }: { children: React.ReactNode }) {
  const [textChatOpen, setTextChatOpenState] = useState(false);
  const setTextChatOpen = useCallback((open: boolean) => {
    setTextChatOpenState(open);
  }, []);

  const value = useMemo(
    () => ({ textChatOpen, setTextChatOpen }),
    [textChatOpen, setTextChatOpen],
  );

  return (
    <CedOverlayContext.Provider value={value}>{children}</CedOverlayContext.Provider>
  );
}

export function useCedOverlay() {
  const ctx = useContext(CedOverlayContext);
  if (!ctx) {
    return { textChatOpen: false, setTextChatOpen: () => {} };
  }
  return ctx;
}
