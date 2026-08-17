"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  applyCedTheme,
  readStoredCedTheme,
  type CedTheme,
} from "@/lib/theme/cedTheme";

type CedThemeContextValue = {
  theme: CedTheme;
  setTheme: (theme: CedTheme) => void;
};

const CedThemeContext = createContext<CedThemeContextValue | null>(null);

export function CedThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<CedTheme>("petrol");

  useEffect(() => {
    const next = readStoredCedTheme();
    setThemeState(next);
    applyCedTheme(next);
  }, []);

  const setTheme = useCallback((next: CedTheme) => {
    setThemeState(next);
    applyCedTheme(next);
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);

  return (
    <CedThemeContext.Provider value={value}>{children}</CedThemeContext.Provider>
  );
}

export function useCedTheme(): CedThemeContextValue {
  const ctx = useContext(CedThemeContext);
  if (!ctx) {
    throw new Error("useCedTheme must be used within CedThemeProvider");
  }
  return ctx;
}
